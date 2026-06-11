import csv
import hashlib
import re
import shutil
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from sourcing import erp_image_search
from sourcing.collect.api_common import write_csv
from sourcing.rerank.embed import build_embedder, embed_source, rerank_image_search


STANDARD_FIELDS = [
    "source_rank", "sku", "product_name", "brand", "category", "image_url",
    "local_image_path", "price", "product_url", "sales", "sales_1y",
    "sales_7d", "review_count", "comments_1y", "rating", "weekly_growth",
    "first_found_at", "avg_daily_sales_1y", "fulfillment_type",
    "seller_name", "seller_url", "weight", "ranked_at", "previous_rank",
    "category_path",
]


def batch_input_dir(base_dir: str | Path, platform: str, product_type: str, batch: str) -> Path:
    return Path(base_dir) / "input" / "platform_exports" / platform / product_type / batch


def batch_output_dir(base_dir: str | Path, platform: str, product_type: str, batch: str) -> Path:
    return Path(base_dir) / "output" / "platform_export_match" / platform / product_type / batch


def work_dir(base_dir: str | Path, platform: str, product_type: str, batch: str) -> Path:
    return batch_output_dir(base_dir, platform, product_type, batch) / "_work"


def infer_aliexpress_image_url(filename: str, base_url: str = "https://ae-pic-a1.aliexpress-media.com/kf/") -> str:
    filename = (filename or "").strip().replace("\\", "/").split("/")[-1]
    if not filename:
        return ""
    return base_url.rstrip("/") + "/" + filename


def _row_image_filenames(html: str, n_rows: int) -> list[str]:
    """逐 <tr> 取该行行内的 ./images 图片文件名，保证"行↔图"严格对齐。

    旧做法用全局 image_refs[index]：某行缺图就会让后面所有行图片整体错位，
    且不报错(静默错配，整份报告作废还看不出来)。改为行内取图后：
      - 某行缺图 -> 只有该行为空，后续行不受影响
      - 数据行数与表格行数对不上 -> 抛 ValueError，拒绝静默错配
    """
    tr_blocks = re.findall(r"<tr[\s>].*?</tr>", html, flags=re.I | re.S)
    # pandas.read_html 恒把首个 <tr> 当表头消费掉，故数据行 = 其余 <tr>
    data_trs = tr_blocks[1:]
    if len(data_trs) != n_rows:
        raise ValueError(
            f"表格数据行数({len(data_trs)})与解析出的商品行数({n_rows})对不上，"
            f"无法保证图片与商品一一对应，已中止以防静默错配。请检查 source.xls。"
        )
    filenames = []
    for tr in data_trs:
        match = re.search(r"<img\s+src=['\"]\.\/images\/([^'\"]+)['\"]", tr, flags=re.I)
        filenames.append(match.group(1) if match else "")
    return filenames


# ===== 一键自动：从下载文件夹直接整理 + 跑全流程(无需手动定 slug/batch/metadata) =====

_PRODUCT_DIR_RE = re.compile(r"^Product[_\d]", re.I)


def _derive_slug(name: str) -> str:
    """中文品类名 → 可读的 ascii slug(内部文件夹/嵌入缓存命名用)。
    中文转拼音(如 汽车及零配件 -> qichejilingpeijian)便于一眼识别，
    再加 6 位哈希后缀保证稳定且不撞。"""
    name = (name or "").strip()
    try:
        from pypinyin import lazy_pinyin
        text = "".join(lazy_pinyin(name))  # 中文转拼音，ascii 原样保留
    except Exception:
        text = name  # 没装 pypinyin 则退回原文(纯中文会落到哈希分支)
    ascii_part = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
    return f"{ascii_part}_{digest}" if ascii_part else f"cat_{digest}"


def _derive_batch(inner_name: str, *, today: date | None = None) -> str:
    """从内层目录名(如 Product_2026_6_10_9_02_55_week)解析日期 → 2026-06-10_week；
    解析不到则用今天。"""
    match = re.search(r"(\d{4})_(\d{1,2})_(\d{1,2})", inner_name or "")
    if match:
        year, month, day = (int(x) for x in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}_week"
    return (today or date.today()).strftime("%Y-%m-%d_week")


def _derive_category_name(src: str | Path) -> str:
    """拖进来的文件夹名即中文品类名；若拖的是最内层 Product_xxx 目录，则取其父目录名。"""
    path = Path(src)
    if _PRODUCT_DIR_RE.match(path.name):
        return path.parent.name
    return path.name


def _find_export_source(root: str | Path) -> tuple[Path, Path, str]:
    """在 root 下(含自身及子目录)找到同时含 *.xls 与 images/ 的目录。
    返回 (xls路径, images目录, 该目录名)。找不到抛 FileNotFoundError。"""
    root = Path(root)
    candidates = [root, *(p for p in root.rglob("*") if p.is_dir())]
    for directory in candidates:
        xls_files = sorted(directory.glob("*.xls"))
        if xls_files and (directory / "images").is_dir():
            return xls_files[0], directory / "images", directory.name
    raise FileNotFoundError(f"在 {root} 下找不到同时含 .xls 和 images/ 的目录")


def prepare_from_download(src: str | Path, *, base_dir: str | Path,
                          platform: str = "ixspy") -> dict:
    """从原始下载文件夹自动整理到标准输入目录(拷 source.xls + images + 写 metadata.yaml)。
    自动推导 中文品类名 / slug / 批次。返回 dict(platform, product_type=slug, batch, product_type_name, input_dir)。"""
    xls_path, images_dir, inner_name = _find_export_source(src)
    category_name = _derive_category_name(src)
    slug = _derive_slug(category_name)
    batch = _derive_batch(inner_name)

    dst = batch_input_dir(base_dir, platform, slug, batch)
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(xls_path, dst / "source.xls")
    dst_images = dst / "images"
    if dst_images.exists():
        shutil.rmtree(dst_images)
    shutil.copytree(images_dir, dst_images)

    metadata = (
        f"platform: {platform}\n"
        f"product_type: {slug}\n"
        f"product_type_name: {category_name}\n"
        f"source: 速卖通产品-新品增长榜\n"
        f"period: {batch}\n"
        f"downloaded_at: {date.today().isoformat()}\n"
        f"original_source:\n"
        f"  directory: {Path(src)}\n"
        f"  table_file: {xls_path.name}\n"
        f"standardized_files:\n"
        f"  table_file: source.xls\n"
        f"  image_dir: images\n"
        f"image_url_infer:\n"
        f"  enabled: true\n"
        f"  base_url: https://ae-pic-a1.aliexpress-media.com/kf/\n"
    )
    (dst / "metadata.yaml").write_text(metadata, encoding="utf-8")

    return {
        "platform": platform,
        "product_type": slug,
        "batch": batch,
        "product_type_name": category_name,
        "input_dir": str(dst),
    }


def default_base_dir() -> str:
    """平台导出数据恒落在本项目下(此文件在 src/sourcing/，上溯两级即项目根)，
    免去手动设 COLLECT_518_DIR。"""
    return str(Path(__file__).resolve().parents[2])


def run_from_download(src: str | Path, *, base_dir: str | Path | None = None,
                      platform: str = "ixspy", source: str = "ixspy",
                      limit: int | None = None, delay_seconds: float = 0.5,
                      threshold: float = 0.85) -> dict:
    """一键：原始下载文件夹 → 整理 → 解析 → 双筛 → 报告。返回流程结果(含 auto 推导信息)。"""
    base_dir = base_dir or default_base_dir()
    info = prepare_from_download(src, base_dir=base_dir, platform=platform)
    result = run_platform_export_pipeline(
        base_dir=base_dir, platform=platform, product_type=info["product_type"],
        batch=info["batch"], source=source, limit=limit,
        delay_seconds=delay_seconds, threshold=threshold)
    result["auto"] = info
    result["report_dir"] = str(batch_output_dir(base_dir, platform, info["product_type"], info["batch"]))
    return result


def read_platform_export(batch_dir: str | Path, *, image_base_url: str | None = None) -> tuple[list[dict], list[dict]]:
    batch_path = Path(batch_dir)
    source_path = batch_path / "source.xls"
    image_dir = batch_path / "images"
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if not image_dir.exists():
        raise FileNotFoundError(image_dir)

    html = source_path.read_text(encoding="utf-8", errors="ignore")
    table = pd.read_html(source_path)[0].fillna("")
    original_rows = table.astype(str).to_dict("records")
    # 行内取图 + 对齐校验，避免某行缺图导致后续整体错位的静默错配
    image_refs = _row_image_filenames(html, len(original_rows))

    metadata = _read_metadata(batch_path / "metadata.yaml")
    product_type_name = metadata.get("product_type_name", "")
    base_url = image_base_url or metadata.get("image_url_infer.base_url") or "https://ae-pic-a1.aliexpress-media.com/kf/"
    standard_rows = []
    for index, original in enumerate(original_rows):
        filename = image_refs[index] if index < len(image_refs) else ""
        local_image_path = str((image_dir / filename).resolve()) if filename else ""
        sku = _clean(original.get("商品id", "")).replace("&nbsp", "").strip()
        sales_1y = _clean(original.get("近一年销量", ""))
        comments = _clean(original.get("累计评论数", ""))
        standard_rows.append(
            {
                "source_rank": _clean(original.get("排名", "")),
                "sku": sku,
                "product_name": _clean(original.get("商品名", "")),
                "brand": _clean(original.get("品牌", "")),
                "category": product_type_name,
                "image_url": infer_aliexpress_image_url(filename, base_url),
                "local_image_path": local_image_path,
                "price": _clean(original.get("商品价格", "")),
                "product_url": _clean(original.get("产品地址", "")),
                "sales": sales_1y,
                "sales_1y": sales_1y,
                "sales_7d": _clean(original.get("七天销量", "")),
                "review_count": comments,
                "comments_1y": comments,
                "rating": _clean(original.get("评分", "")),
                "weekly_growth": _clean(original.get("销量增长数", "")),
                "first_found_at": _clean(original.get("首次发现", "")),
                "avg_daily_sales_1y": _avg_daily_sales(sales_1y),
                "fulfillment_type": _clean(original.get("托管产品", "")),
                "seller_name": _clean(original.get("店铺名称", "")),
                "seller_url": _clean(original.get("店铺地址", "")),
                "weight": _clean(original.get("重量", "")),
                "ranked_at": _clean(original.get("排行时间", "")),
                "previous_rank": _clean(original.get("上次排名", "")),
                "category_path": _clean(original.get("分类路径", "")),
            }
        )
    return original_rows, standard_rows


def prepare_standard_input(
    *,
    base_dir: str | Path,
    platform: str,
    product_type: str,
    batch: str,
    source: str = "ixspy",
) -> dict:
    input_dir = batch_input_dir(base_dir, platform, product_type, batch)
    original_rows, standard_rows = read_platform_export(input_dir)
    batch_out = batch_output_dir(base_dir, platform, product_type, batch)
    batch_out.mkdir(parents=True, exist_ok=True)

    standard_csv = batch_out / "standardized_aliexpress_products.csv"
    write_csv(str(standard_csv), standard_rows, STANDARD_FIELDS)

    staging = work_dir(base_dir, platform, product_type, batch)
    staging_input = staging / "input" / "aliexpress" / product_type
    staging_input.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(standard_csv, staging_input / "aliexpress_products.csv")

    return {
        "source": source,
        "product_type": product_type,
        "batch_input": str(input_dir),
        "standard_csv": str(standard_csv),
        "staging_base_dir": str(staging),
        "rows": len(standard_rows),
        "original_rows": len(original_rows),
    }


def run_platform_export_pipeline(
    *,
    base_dir: str | Path,
    platform: str,
    product_type: str,
    batch: str,
    source: str = "ixspy",
    limit: int | None = None,
    delay_seconds: float = 0.5,
    threshold: float = 0.85,
) -> dict:
    prepared = prepare_standard_input(
        base_dir=base_dir,
        platform=platform,
        product_type=product_type,
        batch=batch,
        source=source,
    )
    staging = prepared["staging_base_dir"]
    search = erp_image_search.run_image_search(
        source=source,
        product_type=product_type,
        base_dir=staging,
        limit=limit,
        delay_seconds=delay_seconds,
    )
    rerank = rerank_image_search(
        source=source,
        product_type=product_type,
        base_dir=staging,
        threshold=threshold,
    )
    decision = erp_image_search.generate_boss_decision_report(
        source=source,
        product_type=product_type,
        base_dir=staging,
    )
    best = erp_image_search.generate_best_match_report(
        source=source,
        product_type=product_type,
        base_dir=staging,
    )
    final = write_final_reports(
        base_dir=base_dir,
        platform=platform,
        product_type=product_type,
        batch=batch,
        source=source,
        staging_base_dir=staging,
    )
    return {
        **prepared,
        "search": search,
        "rerank": rerank,
        "decision": decision,
        "best": best,
        "final": final,
    }


def finalize_platform_export_pipeline(
    *,
    base_dir: str | Path,
    platform: str,
    product_type: str,
    batch: str,
    source: str = "ixspy",
    threshold: float = 0.85,
    limit: int | None = None,
    chunk_size: int = 25,
) -> dict:
    staging = work_dir(base_dir, platform, product_type, batch)
    rerank = rerank_existing_results_resumable(
        source=source,
        product_type=product_type,
        base_dir=str(staging),
        threshold=threshold,
        limit=limit,
        chunk_size=chunk_size,
    )
    decision = erp_image_search.generate_boss_decision_report(
        source=source,
        product_type=product_type,
        base_dir=staging,
    )
    best = erp_image_search.generate_best_match_report(
        source=source,
        product_type=product_type,
        base_dir=staging,
    )
    final = write_final_reports(
        base_dir=base_dir,
        platform=platform,
        product_type=product_type,
        batch=batch,
        source=source,
        staging_base_dir=staging,
    )
    return {
        "source": source,
        "product_type": product_type,
        "staging_base_dir": str(staging),
        "rerank": rerank,
        "decision": decision,
        "best": best,
        "final": final,
    }


def rerank_existing_results_resumable(
    *,
    source: str,
    product_type: str,
    base_dir: str | Path,
    threshold: float = 0.85,
    limit: int | None = None,
    chunk_size: int = 25,
) -> dict:
    path = erp_image_search.output_csv_path(base_dir, source, product_type)
    rows = _read_csv_dicts(path)
    if limit is not None:
        rows = rows[:limit]

    get_embedding, matcher = build_embedder(product_type=product_type)
    embedding_cache = {}
    processed = 0
    skipped = 0
    errors = 0

    for index, row in enumerate(rows):
        if row.get("embedding_similarity") or row.get("embedding_confident") in {"0", "1"}:
            skipped += 1
            continue
        try:
            query = _embedding_for(
                row.get("external_image_url"),
                embed_source(row.get("source")),
                get_embedding,
                embedding_cache,
            )
            candidate = _embedding_for(
                row.get("erp_image_url"),
                "erp",
                get_embedding,
                embedding_cache,
            )
            sim = _cosine(query, candidate)
            row["embedding_similarity"] = "" if sim is None else round(sim, 4)
            row["embedding_confident"] = "1" if (sim is not None and sim >= threshold) else "0"
        except Exception as error:
            errors += 1
            row["embedding_similarity"] = ""
            row["embedding_confident"] = "0"
            row["embedding_error"] = f"{type(error).__name__}: {error}"
        processed += 1

        if processed % max(1, chunk_size) == 0:
            _write_rerank_rows(path, rows, matcher)

    _write_rerank_rows(path, rows, matcher)
    confident = sum(1 for row in rows if row.get("embedding_confident") == "1")
    return {
        "reranked": processed,
        "skipped": skipped,
        "errors": errors,
        "confident": confident,
        "output": str(path),
    }


def _embedding_for(url, source, get_embedding, cache):
    if not url:
        return None
    key = (url, source)
    if key not in cache:
        cache[key] = get_embedding(url, source)
    return cache[key]


def _cosine(left, right):
    if left is None or right is None:
        return None
    return float(left @ right)


def _write_rerank_rows(path: str | Path, rows: list[dict], matcher):
    fields = erp_image_search._fields_with_extras(
        list(erp_image_search.RESULT_FIELDS) + ["embedding_similarity", "embedding_confident", "embedding_error"],
        rows,
    )
    write_csv(str(path), rows, fields)
    cache = getattr(matcher, "cache", None) if matcher is not None else None
    if cache is not None and hasattr(cache, "flush"):
        cache.flush()


def write_final_reports(
    *,
    base_dir: str | Path,
    platform: str,
    product_type: str,
    batch: str,
    source: str,
    staging_base_dir: str | Path,
) -> dict:
    batch_dir = batch_input_dir(base_dir, platform, product_type, batch)
    batch_out = batch_output_dir(base_dir, platform, product_type, batch)
    original_rows, standard_rows = read_platform_export(batch_dir)
    metadata = _read_metadata(batch_dir / "metadata.yaml")
    result_rows = _read_csv_dicts(erp_image_search.output_csv_path(staging_base_dir, source, product_type))
    best_by_sku = _best_result_by_sku(result_rows)

    final_rows = []
    for original, standard in zip(original_rows, standard_rows):
        sku = standard["sku"]
        result = best_by_sku.get(sku, {})
        sim = _safe_float(result.get("embedding_similarity"))
        final_rows.append(
            {
                **original,
                "竞品图片链接": standard.get("image_url", ""),
                "竞品本地图片": standard.get("local_image_path", ""),
                "标准化SKU": sku,
                "标准化类目": standard.get("category", ""),
                "分类路径": standard.get("category_path", original.get("分类路径", "")),
                "近一年日均销量": standard.get("avg_daily_sales_1y", ""),
                "ERP搜索状态": result.get("match_status", ""),
                "最像ERP_SKU": result.get("matched_erp_sku", ""),
                "ERP主SKU": result.get("matched_main_sku", ""),
                "ERP商品状态": result.get("erp_product_status_text", ""),
                "ERP候选图": result.get("erp_image_url", ""),
                "ERP以图搜索相似度": result.get("similarity", ""),
                "模型精筛相似度": "" if sim < 0 else round(sim, 4),
                "匹配判定": _match_verdict(sim),
                "老板建议": _boss_advice(result, sim),
                "图搜错误信息": result.get("message", ""),
            }
        )

    csv_path = batch_out / "matched_report.csv"
    xlsx_path = batch_out / _boss_report_filename(metadata.get("product_type_name") or product_type)
    pd.DataFrame(final_rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(final_rows).to_excel(xlsx_path, index=False)

    shutil.copyfile(
        erp_image_search.output_csv_path(staging_base_dir, source, product_type),
        batch_out / "raw_erp_image_search.csv",
    )
    shutil.copyfile(
        erp_image_search.boss_decision_csv_path(staging_base_dir, source, product_type),
        batch_out / "boss_decision_report.csv",
    )
    shutil.copyfile(
        erp_image_search.best_match_csv_path(staging_base_dir, source, product_type),
        batch_out / "best_match_report.csv",
    )
    return {
        "matched_csv": str(csv_path),
        "boss_xlsx": str(xlsx_path),
        "products": len(final_rows),
        "matched": sum(1 for row in final_rows if row.get("最像ERP_SKU")),
    }


def _best_result_by_sku(rows: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row.get("external_sku", ""), []).append(row)
    best = {}
    for sku, items in groups.items():
        candidates = [item for item in items if item.get("erp_image_url")] or items
        best[sku] = max(candidates, key=lambda row: _safe_float(row.get("embedding_similarity")))
    return best


def _read_csv_dicts(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _boss_report_filename(product_name: str) -> str:
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", _clean(product_name)).strip(" ._")
    safe_name = safe_name or "商品"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_name}_{timestamp}.xlsx"


def _clean(value) -> str:
    text = "" if value is None else str(value)
    return "" if text.lower() == "nan" else text.strip()


def _read_metadata(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, value = raw.strip().split(":", 1)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        full_key = ".".join([item[1] for item in stack] + [key])
        value = value.strip().strip('"').strip("'")
        if value:
            out[full_key] = value
        else:
            stack.append((indent, key))
    return out


def _avg_daily_sales(value: str) -> str:
    try:
        return str(round(float(str(value).replace(",", "")) / 365))
    except (TypeError, ValueError):
        return ""


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _match_verdict(sim: float) -> str:
    if sim < 0:
        return "无图或精筛失败"
    if sim >= 0.85:
        return "高置信匹配"
    if sim >= 0.70:
        return "可能匹配"
    if sim >= 0.50:
        return "弱匹配(需人工)"
    return "无匹配(疑似不同款)"


def _boss_advice(result: dict, sim: float) -> str:
    if not result:
        return "未完成图搜，需补跑"
    if result.get("match_status") == "error":
        return "图搜失败，需补搜或人工确认"
    if sim >= 0.85:
        return "疑似ERP已有同款，确认后不建议作为新品开发"
    if sim >= 0.50:
        return "存在相似款，建议人工复核差异点"
    return "疑似新品机会，可进入选品池继续评估"
