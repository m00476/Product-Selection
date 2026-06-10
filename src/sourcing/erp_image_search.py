import csv
import json
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sourcing.collect.api_common import write_csv


DEFAULT_API_URL = "http://103.198.125.2:8077/Api/prodetail/picSearchFunds"
DEFAULT_URL_API_URL = "http://103.198.125.2:16777/open/pic/searchProductByPicUrl"
RESULT_FIELDS = [
    "source",
    "product_type",
    "external_sku",
    "external_product_name",
    "external_product_url",
    "external_image_url",
    "external_source_rank",
    "external_brand",
    "external_category",
    "external_price",
    "external_sales",
    "external_sales_1y",
    "external_sales_7d",
    "external_review_count",
    "external_comments_1y",
    "external_rating",
    "external_weekly_growth",
    "external_first_found_at",
    "external_avg_daily_sales_1y",
    "external_fulfillment_type",
    "external_choice",
    "external_choice_type",
    "external_seller_id",
    "external_seller_name",
    "external_seller_positive_rate",
    "match_status",
    "matched_erp_sku",
    "matched_main_sku",
    "erp_product_status",
    "erp_product_status_text",
    "candidate_priority",
    "erp_image_url",
    "similarity",
    "message",
    "code",
    "trace_id",
    "searched_at",
    "raw_json",
]

BOSS_DECISION_FIELDS = [
    "source",
    "product_type",
    "external_sku",
    "external_product_name",
    "external_product_url",
    "external_image_url",
    "external_source_rank",
    "external_brand",
    "external_category",
    "external_price",
    "external_sales",
    "external_sales_1y",
    "external_sales_7d",
    "external_review_count",
    "external_comments_1y",
    "external_rating",
    "external_weekly_growth",
    "external_first_found_at",
    "external_avg_daily_sales_1y",
    "external_fulfillment_type",
    "external_choice",
    "external_choice_type",
    "external_seller_id",
    "external_seller_name",
    "external_seller_positive_rate",
    "final_decision",
    "boss_action",
    "candidate_count",
    "normal_candidate_count",
    "stopped_candidate_count",
    "limited_candidate_count",
    "risk_candidate_count",
    "top_erp_skus",
    "top_main_skus",
    "max_embedding_similarity",
]

BOSS_DECISION_FIELD_LABELS = {
    "source": "数据来源",
    "product_type": "商品类型",
    "external_sku": "外部平台SKU",
    "external_product_name": "外部平台商品标题",
    "external_product_url": "外部平台商品链接",
    "external_image_url": "外部平台主图链接",
    "external_source_rank": "外部平台排序",
    "external_brand": "外部平台品牌",
    "external_category": "外部平台类目",
    "external_price": "外部平台价格",
    "external_sales": "外部平台累计销量",
    "external_sales_1y": "近一年销量",
    "external_sales_7d": "近7天销量",
    "external_review_count": "外部平台评论数",
    "external_comments_1y": "近一年评论数",
    "external_rating": "外部平台评分",
    "external_weekly_growth": "周增长数",
    "external_first_found_at": "首次发现时间",
    "external_avg_daily_sales_1y": "近一年日均销量",
    "external_fulfillment_type": "托管类型",
    "external_choice": "托管标记",
    "external_choice_type": "托管类型原始值",
    "external_seller_id": "外部平台卖家ID",
    "external_seller_name": "外部平台卖家名称",
    "external_seller_positive_rate": "外部平台卖家好评率",
    "final_decision": "系统判断",
    "boss_action": "建议动作",
    "candidate_count": "ERP候选数量",
    "normal_candidate_count": "ERP正常同款数量",
    "stopped_candidate_count": "ERP停产同款数量",
    "limited_candidate_count": "ERP采购受限同款数量",
    "risk_candidate_count": "ERP风险同款数量",
    "top_erp_skus": "最相似ERP SKU",
    "top_main_skus": "对应ERP主SKU",
    "max_embedding_similarity": "最高图片相似度",
}

PRODUCT_STATUS_MAP = {
    "1": "停产商品",
    "2": "清仓商品",
    "4": "侵权风险商品",
    "5": "站点违规风险商品",
    "6": "采购不到商品",
    "7": "自动创建",
    "8": "正常商品",
    "9": "质量差商品",
    "10": "暂时采购不到商品",
    "11": "禁运产品",
    "12": "GBC侵权",
    "13": "疑似侵权",
    "14": "违禁品商品",
}


@dataclass
class SearchResult:
    status: str
    code: int | None
    message: str
    trace_id: str
    matches: list[dict]
    raw: dict


class ErpImageSearchClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.token = token if token is not None else os.environ.get("ERP_IMAGE_SEARCH_TOKEN", "")
        self.url_api_token = os.environ.get("ERP_IMAGE_SEARCH_BY_URL_TOKEN", "")
        self.url_api_url = os.environ.get("ERP_IMAGE_SEARCH_BY_URL_URL", "")
        if not self.token and not self.url_api_token:
            raise RuntimeError("ERP_IMAGE_SEARCH_TOKEN not set")
        self.api_url = api_url or os.environ.get("ERP_IMAGE_SEARCH_URL", DEFAULT_API_URL)
        self.timeout = timeout

    def search(self, image_url: str) -> SearchResult:
        if self.url_api_token:
            return self._search_by_url(image_url)
        image_bytes, filename, content_type = self._download_image(image_url)
        body, boundary = _build_multipart_body(
            fields={"fileUrls": "undefined"},
            files={"files": (filename, image_bytes, content_type)},
        )
        request = Request(
            self.api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": self.token,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as err:
            raw_text = err.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = {"code": err.code, "msg": raw_text[:500], "data": []}
            return normalize_search_response(payload)

        return normalize_search_response(json.loads(raw_text))

    def _search_by_url(self, image_url: str) -> SearchResult:
        if not image_url or not image_url.lower().startswith(("http://", "https://")):
            raise RuntimeError("external image_url must start with http:// or https://")
        body = json.dumps({"picUrl": image_url}, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.url_api_url or DEFAULT_URL_API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": self.url_api_token,
                "Content-Type": "application/json;charset=UTF-8",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as err:
            raw_text = err.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = {"code": err.code, "msg": raw_text[:500], "data": []}
            return normalize_search_response(payload)

        return normalize_search_response(json.loads(raw_text))

    def _download_image(self, image_url: str) -> tuple[bytes, str, str]:
        if not image_url or not image_url.lower().startswith(("http://", "https://")):
            raise RuntimeError("external image_url must start with http:// or https://")
        request = Request(image_url, headers={"User-Agent": "ProductSourcingSystem/0.1"})
        with urlopen(request, timeout=self.timeout) as response:
            data = response.read()
            content_type = response.headers.get_content_type() or "image/jpeg"
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        return data, f"erp-search-image{extension}", content_type


def input_csv_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    filename_by_source = {
        "seerfar": "seerfar_products.csv",
        "ixspy": "aliexpress_products.csv",
        "aliexpress": "aliexpress_products.csv",
    }
    directory_by_source = {
        "seerfar": "seerfar",
        "ixspy": "aliexpress",
        "aliexpress": "aliexpress",
    }
    if source not in filename_by_source:
        raise RuntimeError(f"Unsupported image-search source: {source}")
    return (
        Path(base_dir)
        / "input"
        / directory_by_source[source]
        / product_type
        / filename_by_source[source]
    )


def output_csv_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "erp_image_search_results.csv"


def boss_decision_csv_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "boss_decision_report.csv"


def boss_decision_markdown_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "boss_decision_report.md"


def load_external_rows(path: str | Path, *, source: str, product_type: str) -> list[dict]:
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            image_url = (row.get("image_url") or "").strip()
            if not image_url:
                continue
            external = {
                "source": source,
                "product_type": product_type,
                "external_sku": (row.get("sku") or "").strip(),
                "external_product_name": (row.get("product_name") or "").strip(),
                "external_product_url": (row.get("product_url") or "").strip(),
                "external_image_url": image_url,
            }
            for key, value in row.items():
                external[f"external_{key}"] = (value or "").strip()
            rows.append(external)
    return rows


def normalize_search_response(payload: dict) -> SearchResult:
    data = payload.get("data")
    products = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    matches = []
    for product in products:
        if not isinstance(product, dict):
            continue
        matches.append(
            {
                "matched_erp_sku": _first(product, ["sku", "picName", "picname", "imageName", "mainSKu", "mainsku", "mainSku", "main_sku"]),
                "matched_main_sku": _first(product, ["mainSKu", "mainsku", "mainSku", "main_sku"]),
                "erp_product_status": _first(product, ["productStatus", "statusName", "statusText", "status"]),
                "erp_image_url": _first(product, ["url", "picUrl", "imageUrl", "imgUrl", "fileUrl"]),
                "similarity": _number(_first(product, ["similarity", "score"])),
            }
        )
    # ERP 鉴权失败用 {"status":404} 而非 {"code":...}；缺 code 时回退用数字 status 当 code，
    # 否则 404 会被误判成 empty，导致 token 过期时自动刷新无法触发。
    code = payload.get("code")
    if code is None and isinstance(payload.get("status"), int):
        code = payload.get("status")
    status = "success" if code == 200 and matches else "empty"
    if code not in (None, 200):
        status = "error"
    return SearchResult(
        status=status,
        code=code,
        message=str(payload.get("msg") or payload.get("message") or ""),
        trace_id=str(payload.get("traceId") or ""),
        matches=matches,
        raw=payload,
    )


def _default_token_refresher(base_dir: str):
    from sourcing.erp_token import refresh_erp_token  # 懒导入避免循环
    return refresh_erp_token(base_dir)


def _is_auth_failure(result) -> bool:
    """判断图搜结果是否像 token 过期/鉴权失败(而非正常的'没匹配到')。"""
    if getattr(result, "status", None) != "error":
        return False
    message = (getattr(result, "message", "") or "").lower()
    code = getattr(result, "code", None)
    return code in (401, 403, 404) or any(
        kw in message for kw in ("not found", "token", "unauth", "登录", "鉴权"))


def run_image_search(
    *,
    source: str,
    product_type: str,
    base_dir: str | Path = ".",
    limit: int | None = None,
    delay_seconds: float = 0.5,
    search_func=None,
    sleep_func=time.sleep,
    max_retries: int = 3,
    token_refresher=None,
) -> dict:
    input_path = input_csv_path(base_dir, source, product_type)
    rows = load_external_rows(input_path, source=source, product_type=product_type)
    if limit is not None:
        rows = rows[:limit]

    client = None
    if search_func is None:
        client = ErpImageSearchClient()
        search_func = client.search

    refreshed = False
    output_rows = []
    for index, external in enumerate(rows):
        result = _search_with_retries(
            search_func, external["external_image_url"],
            max_retries=max_retries, sleep_func=sleep_func,
        )
        # token 过期自动刷新一次后重试(只刷新一次, 避免反复登录)
        can_refresh = client is not None or token_refresher is not None
        if can_refresh and not refreshed and _is_auth_failure(result):
            refreshed = True
            refresher = token_refresher or _default_token_refresher
            new_token = refresher(str(base_dir))
            if client is not None and new_token:
                client.token = new_token
            result = _search_with_retries(
                search_func, external["external_image_url"],
                max_retries=max_retries, sleep_func=sleep_func,
            )
        output_rows.extend(_result_rows(external, result))
        if delay_seconds > 0 and index < len(rows) - 1:
            sleep_func(delay_seconds)

    output_path = write_csv(str(output_csv_path(base_dir, source, product_type)), output_rows, _fields_with_extras(RESULT_FIELDS, output_rows))
    return {
        "source": source,
        "product_type": product_type,
        "input": str(input_path),
        "output": output_path,
        "searched": len(rows),
        "written": len(output_rows),
    }


def _search_with_retries(search_func, image_url: str, *, max_retries: int, sleep_func=time.sleep) -> SearchResult:
    last_error = None
    for attempt in range(1, max(1, max_retries) + 1):
        try:
            return search_func(image_url)
        except Exception as error:
            last_error = error
            if attempt < max_retries:
                sleep_func(min(2 * attempt, 10))
    message = f"{type(last_error).__name__}: {last_error}" if last_error else "unknown error"
    return SearchResult(
        status="error",
        code=None,
        message=message,
        trace_id="",
        matches=[],
        raw={"error": message},
    )


def generate_boss_decision_report(
    *,
    source: str,
    product_type: str,
    base_dir: str | Path = ".",
) -> dict:
    input_path = output_csv_path(base_dir, source, product_type)
    rows = _read_csv_dicts(input_path)
    decisions = build_boss_decision_rows(rows)
    fields = _fields_with_extras(BOSS_DECISION_FIELDS, decisions)
    csv_path = write_csv(
        str(boss_decision_csv_path(base_dir, source, product_type)),
        _localized_rows(decisions, BOSS_DECISION_FIELD_LABELS),
        [_field_label(field, BOSS_DECISION_FIELD_LABELS) for field in fields],
    )
    markdown_path = boss_decision_markdown_path(base_dir, source, product_type)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_boss_decision_markdown(decisions, source, product_type), encoding="utf-8")
    return {
        "source": source,
        "product_type": product_type,
        "input": str(input_path),
        "csv": csv_path,
        "markdown": str(markdown_path),
        "products": len(decisions),
    }


def build_boss_decision_rows(rows: list[dict]) -> list[dict]:
    groups = {}
    order = []
    for row in rows:
        key = (
            row.get("source") or "",
            row.get("product_type") or "",
            row.get("external_sku") or "",
            row.get("external_product_url") or "",
            row.get("external_image_url") or "",
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    decisions = []
    for key in order:
        items = groups[key]
        first = items[0]
        normal = _count_priority(items, "可用正常商品")
        stopped = _count_priority(items, "疑似同款但停产")
        limited = _count_priority(items, "疑似同款但采购受限")
        risk = _count_priority(items, "疑似同款但风险商品")
        final_decision, boss_action = _boss_decision(normal, stopped, limited, risk, items)
        decisions.append(
            {
                "source": first.get("source", ""),
                "product_type": first.get("product_type", ""),
                "external_sku": first.get("external_sku", ""),
                "external_product_name": first.get("external_product_name", ""),
                "external_product_url": first.get("external_product_url", ""),
                "external_image_url": first.get("external_image_url", ""),
                "external_source_rank": first.get("external_source_rank", ""),
                "external_brand": first.get("external_brand", ""),
                "external_category": first.get("external_category", ""),
                "external_price": first.get("external_price", ""),
                "external_sales": first.get("external_sales", ""),
                "external_sales_1y": first.get("external_sales_1y", ""),
                "external_sales_7d": first.get("external_sales_7d", ""),
                "external_review_count": first.get("external_review_count", ""),
                "external_comments_1y": first.get("external_comments_1y", ""),
                "external_rating": first.get("external_rating", ""),
                "external_weekly_growth": first.get("external_weekly_growth", ""),
                "external_first_found_at": first.get("external_first_found_at", ""),
                "external_avg_daily_sales_1y": first.get("external_avg_daily_sales_1y", ""),
                "external_fulfillment_type": first.get("external_fulfillment_type", ""),
                "external_choice": first.get("external_choice", ""),
                "external_choice_type": first.get("external_choice_type", ""),
                "external_seller_id": first.get("external_seller_id", ""),
                "external_seller_name": first.get("external_seller_name", ""),
                "external_seller_positive_rate": first.get("external_seller_positive_rate", ""),
                "final_decision": final_decision,
                "boss_action": boss_action,
                "candidate_count": len([item for item in items if item.get("matched_erp_sku")]),
                "normal_candidate_count": normal,
                "stopped_candidate_count": stopped,
                "limited_candidate_count": limited,
                "risk_candidate_count": risk,
                "top_erp_skus": _join_unique(items, "matched_erp_sku"),
                "top_main_skus": _join_unique(items, "matched_main_sku"),
                "max_embedding_similarity": _max_embedding(items),
            }
        )
    return decisions


def render_boss_decision_markdown(decisions: list[dict], source: str, product_type: str) -> str:
    lines = [
        "# ERP 以图搜索老板决策报告",
        "",
        f"数据来源：{source}",
        f"品类：{product_type}",
        "",
        "## 决策摘要",
        "",
        "| 平台SKU | 商品名称 | 价格 | 近一年销量 | 近一年评论 | 7天销量 | 周增长 | 日均销量 | 首次发现 | 托管类型 | 结论 | 建议动作 | ERP候选 | 正常候选 | 停产候选 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in decisions:
        lines.append(
            "| {external_sku} | {external_product_name} | {external_price} | {external_sales} | "
            "{external_review_count} | {external_sales_7d} | {external_weekly_growth} | "
            "{external_avg_daily_sales_1y} | {external_first_found_at} | {external_fulfillment_type} | "
            "{final_decision} | {boss_action} | "
            "{candidate_count} | {normal_candidate_count} | {stopped_candidate_count} |".format(
                **{key: _md_cell(value) for key, value in row.items()}
            )
        )

    lines.extend(["", "## 明细", ""])
    for row in decisions:
        lines.extend(
            [
                f"### {row.get('external_sku') or '无平台SKU'}",
                "",
                f"- 商品名称：{row.get('external_product_name') or '-'}",
                f"- 外部平台价格：{row.get('external_price') or '-'}",
                f"- 近一年销量：{row.get('external_sales') or '-'}",
                f"- 近一年评论数：{row.get('external_review_count') or '-'}",
                f"- 近 7 天销量：{row.get('external_sales_7d') or '-'}",
                f"- 周增长数：{row.get('external_weekly_growth') or '-'}",
                f"- 近一年日均销量：{row.get('external_avg_daily_sales_1y') or '-'}",
                f"- 首次发现时间：{row.get('external_first_found_at') or '-'}",
                f"- 托管类型：{row.get('external_fulfillment_type') or '-'}",
                f"- 评分：{row.get('external_rating') or '-'}",
                f"- 店铺：{row.get('external_seller_name') or '-'}",
                f"- 最终结论：{row.get('final_decision')}",
                f"- 建议动作：{row.get('boss_action')}",
                f"- ERP 候选 SKU：{row.get('top_erp_skus') or '-'}",
                f"- ERP 主 SKU：{row.get('top_main_skus') or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def _result_rows(external: dict, result: SearchResult) -> list[dict]:
    searched_at = datetime.now(timezone.utc).isoformat()
    raw_json = json.dumps(result.raw, ensure_ascii=False, sort_keys=True)
    matches = result.matches or [{}]
    rows = []
    for match in matches:
        status_code = str(match.get("erp_product_status", "") or "")
        status_text = format_product_status(status_code)
        rows.append(
            {
                **external,
                "match_status": result.status,
                "matched_erp_sku": match.get("matched_erp_sku", ""),
                "matched_main_sku": match.get("matched_main_sku", ""),
                "erp_product_status": status_code,
                "erp_product_status_text": status_text,
                "candidate_priority": candidate_priority(result.status, status_code),
                "erp_image_url": match.get("erp_image_url", ""),
                "similarity": match.get("similarity", ""),
                "message": result.message,
                "code": result.code if result.code is not None else "",
                "trace_id": result.trace_id,
                "searched_at": searched_at,
                "raw_json": raw_json,
            }
        )
    return rows


def format_product_status(status: str) -> str:
    normalized = str(status or "").strip()
    if not normalized:
        return ""
    return PRODUCT_STATUS_MAP.get(normalized, normalized)


def candidate_priority(match_status: str, product_status: str) -> str:
    if match_status != "success":
        return "需人工确认"
    normalized = str(product_status or "").strip()
    if normalized == "8":
        return "可用正常商品"
    if normalized == "1":
        return "疑似同款但停产"
    if normalized in {"2", "6", "10"}:
        return "疑似同款但采购受限"
    if normalized in {"4", "5", "11", "12", "13", "14"}:
        return "疑似同款但风险商品"
    return "需人工确认"


def _read_csv_dicts(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _count_priority(rows: list[dict], priority: str) -> int:
    return sum(1 for row in rows if (row.get("candidate_priority") or "").strip() == priority)


def _max_embedding(rows: list[dict]):
    vals = []
    for row in rows:
        v = row.get("embedding_similarity")
        if v in (None, "", "None"):
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(vals) if vals else ""


def _boss_decision(
    normal_count: int,
    stopped_count: int,
    limited_count: int,
    risk_count: int,
    rows: list[dict],
) -> tuple[str, str]:
    if normal_count:
        return "疑似已有正常同款", "先人工确认正常候选；确认同款后不要作为新品开发"
    if risk_count:
        return "疑似风险同款", "先走合规审核；未确认前不要推进开发"
    if stopped_count:
        return "有历史停产同款", "查停产原因和供应链；可作为恢复或重新开发机会"
    if limited_count:
        return "有采购受限同款", "先确认采购能否恢复；不能恢复再按新品机会评估"
    if any(row.get("matched_erp_sku") for row in rows):
        return "需人工确认", "候选信息不足；人工确认是否同款"
    return "疑似新品机会", "ERP 未找到明确候选；进入新品机会池继续评估销量和利润"


def _join_unique(rows: list[dict], field: str, limit: int = 5) -> str:
    values = []
    seen = set()
    for row in rows:
        value = (row.get(field) or "").strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
        if len(values) >= limit:
            break
    return ", ".join(values)


def _md_cell(value) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "/").replace("\r", " ").replace("\n", " ")


def _fields_with_extras(base_fields: list[str], rows: list[dict]) -> list[str]:
    fields = list(base_fields)
    seen = set(fields)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def _field_label(field: str, labels: dict[str, str]) -> str:
    return labels.get(field, field)


def _localized_rows(rows: list[dict], labels: dict[str, str]) -> list[dict]:
    return [
        {_field_label(key, labels): value for key, value in row.items()}
        for row in rows
    ]


def _first(product: dict, keys: list[str]) -> str:
    for key in keys:
        value = product.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _number(value: str):
    if value == "":
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return ""


def _build_multipart_body(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----ProductSourcing{uuid.uuid4().hex}"
    chunks = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


# 老板版报告的外部业务字段：报表列名 -> 输入CSV里可能的列名(按序取第一个非空)
_EXTERNAL_BIZ_FIELDS = [
    ("品牌", ["brand"]),
    ("类目", ["category"]),
    ("单价", ["price"]),
    ("近一年销量", ["sales_1y", "sales"]),
    ("近一年评论数", ["comments_1y", "review_count"]),
    ("近7天销量", ["sales_7d"]),
    ("周增长数", ["weekly_growth"]),
    ("首次发现时间", ["first_found_at"]),
    ("近一年日均销量", ["avg_daily_sales_1y"]),
    ("托管类型", ["fulfillment_type"]),
    ("评分", ["rating", "review_rating"]),
    ("卖家", ["seller_name"]),
    ("卖家好评率", ["seller_positive_rate"]),
]

BEST_MATCH_FIELDS = [
    "竞品SKU", "竞品名称", "品牌", "类目", "单价", "近一年销量", "近一年评论数",
    "近7天销量", "周增长数", "首次发现时间", "近一年日均销量", "托管类型",
    "评分", "卖家", "卖家好评率", "竞品图", "竞品链接",
    "最像ERP_SKU", "ERP主SKU", "ERP商品状态", "ERP候选图", "嵌入相似度", "匹配判定",
]


def _biz(row: dict, names: list[str]):
    for name in names:
        value = row.get(name)
        if value not in (None, "", "None"):
            return value
    return ""


def _embedding_value(row: dict) -> float:
    try:
        return float(row.get("embedding_similarity"))
    except (TypeError, ValueError):
        return -1.0


def best_match_verdict(sim: float) -> str:
    if sim < 0:
        return "无图(竞品图失败)"
    if sim >= 0.85:
        return "高置信匹配"
    if sim >= 0.70:
        return "可能匹配"
    if sim >= 0.50:
        return "弱匹配(需人工)"
    return "无匹配(疑似不同款)"


def build_best_match_rows(rows: list[dict], external_index: dict | None = None) -> list[dict]:
    """每个竞品取嵌入相似度最高的候选(B口径: 无匹配也保留最像候选), 输出一商品一行。
    external_index: {external_sku: 输入CSV行} —— 给齐了就把单价/销量等业务字段合进来(老板版)。"""
    external_index = external_index or {}
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        key = row.get("external_sku") or ""
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    out = []
    for key in order:
        items = groups[key]
        candidates = [it for it in items if it.get("erp_image_url")] or items
        best = max(candidates, key=_embedding_value)
        sim = _embedding_value(best)
        ext = external_index.get(key, {})
        out.append({
            "竞品SKU": key,
            "竞品名称": (best.get("external_product_name") or "")[:60],
            **{col: _biz(ext, names) for col, names in _EXTERNAL_BIZ_FIELDS},
            "竞品图": best.get("external_image_url", ""),
            "竞品链接": best.get("external_product_url", ""),
            "最像ERP_SKU": best.get("matched_erp_sku", ""),
            "ERP主SKU": best.get("matched_main_sku", ""),
            "ERP商品状态": best.get("erp_product_status_text", ""),
            "ERP候选图": best.get("erp_image_url", ""),
            "嵌入相似度": round(sim, 4) if sim >= 0 else "",
            "匹配判定": best_match_verdict(sim),
        })
    return out


def best_match_csv_path(base_dir, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "best_match_report.csv"


def _external_index(base_dir, source: str, product_type: str) -> dict:
    """从输入CSV按 sku 建索引，给老板版报告补业务字段。读不到就返回空。"""
    index = {}
    try:
        for row in _read_csv_dicts(input_csv_path(base_dir, source, product_type)):
            sku = (row.get("sku") or "").strip()
            if sku:
                index[sku] = row
    except (FileNotFoundError, OSError):
        pass
    return index


def generate_best_match_report(*, source: str, product_type: str, base_dir="." ) -> dict:
    rows = _read_csv_dicts(output_csv_path(base_dir, source, product_type))
    out = build_best_match_rows(rows, _external_index(base_dir, source, product_type))
    out.sort(key=lambda r: r["嵌入相似度"] if isinstance(r["嵌入相似度"], float) else -1.0,
             reverse=True)
    csv_path = write_csv(str(best_match_csv_path(base_dir, source, product_type)),
                         out, BEST_MATCH_FIELDS)
    verdicts: dict[str, int] = {}
    for r in out:
        verdicts[r["匹配判定"]] = verdicts.get(r["匹配判定"], 0) + 1
    return {"source": source, "product_type": product_type, "products": len(out),
            "verdicts": verdicts, "csv": csv_path}
