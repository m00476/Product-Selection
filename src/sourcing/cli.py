import argparse
import json
from sourcing import config, db, erp_image_search
from sourcing.importer import import_erp_csv, import_ixspy_csv, import_seerfar_csv
from sourcing.analysis.run import run_analysis
from sourcing.quality import inspect_csv_quality
from sourcing.collect.orchestrator import collect_all
from sourcing.bridge.run import bridge_matches
from sourcing.bridge.external_importer import import_external_products
from sourcing.bridge.image_decisions import load_image_decisions
from sourcing.rerank.embed import rerank_image_search
from sourcing.erp_image_pipeline import run_pipeline
from sourcing.platform_export_pipeline import (
    finalize_platform_export_pipeline,
    prepare_standard_input,
    run_platform_export_pipeline,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sourcing pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="导入源 CSV 到 PostgreSQL")
    imp.add_argument("--source", required=True, choices=["seerfar", "ixspy", "erp"])
    imp.add_argument("--path", required=True, help="CSV 文件路径")
    imp.add_argument("--product-type", required=True)

    quality = sub.add_parser("quality", help="检查源 CSV 字段完整性")
    quality.add_argument("--source", required=True, choices=["seerfar", "ixspy", "erp"])
    quality.add_argument("--path", required=True, help="CSV 文件路径")
    quality.add_argument("--product-type", required=True)

    sub.add_parser("analyze", help="计算利润估算与机会分")

    col = sub.add_parser("collect", help="调用采集脚本产出CSV并导入")
    col.add_argument("--source", choices=["seerfar", "ixspy", "erp"],
                     help="单个源（与 --product-type 一起用）")
    col.add_argument("--product-type", help="单个品类")
    col.add_argument("--all", action="store_true", help="按 COLLECT_TARGETS 采集全部")

    sub.add_parser("bridge-matches", help="把 518 匹配结果桥接进 product_matches")

    sub.add_parser("import-external", help="把 518 已抓的竞品(external_products)导入本系统")

    img = sub.add_parser("erp-image-search", help="用外部商品图片调用 ERP 以图搜索")
    img.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    img.add_argument("--product-type", required=True)
    img.add_argument("--limit", type=int, default=20, help="小样本数量；正式跑可调大")
    img.add_argument("--delay", type=float, default=0.5, help="每张图片之间的等待秒数")

    img_report = sub.add_parser("erp-image-decision-report", help="把 ERP 以图搜索结果汇总成老板决策表")
    img_report.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    img_report.add_argument("--product-type", required=True)
    img_report.add_argument("--base-dir", default=".", help="以图搜索结果所在项目目录")

    img_load = sub.add_parser("erp-image-load-db", help="把 ERP 图搜老板决策落进 PostgreSQL")
    img_load.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    img_load.add_argument("--product-type", required=True)

    rr = sub.add_parser("erp-image-rerank", help="用DINOv2嵌入给图搜候选补相似度并卡阈值")
    rr.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    rr.add_argument("--product-type", required=True)
    rr.add_argument("--limit", type=int, default=None)
    rr.add_argument("--threshold", type=float, default=0.85)

    pipe = sub.add_parser("erp-image-pipeline", help="一键: 图搜粗筛+嵌入精配+落库+报告")
    pipe.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    pipe.add_argument("--product-type", required=True)
    pipe.add_argument("--limit", type=int, default=None)
    pipe.add_argument("--threshold", type=float, default=0.85)

    mr = sub.add_parser("erp-image-match-report", help="出 每竞品↔ERP最佳匹配 精准清单(嵌入排序)")
    mr.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    mr.add_argument("--product-type", required=True)
    mr.add_argument("--base-dir", default=None)

    rp = sub.add_parser("run-product", help="一条龙: 采集→图片两层匹配→报告(带退出码+日志,供计划任务调用)")
    rp.add_argument("--source", default="ixspy", choices=["seerfar", "ixspy"])
    rp.add_argument("--product-type", required=True, help="内部英文 slug(决定文件夹/库标签)")
    rp.add_argument("--category", default=None, help="ixspy 类目中文名(写入 ALIEXPRESS_CATEGORY_NAME)")
    rp.add_argument("--headless", action="store_true", help="无界面跑 Chrome(无人值守)")
    rp.add_argument("--limit", type=int, default=None)
    rp.add_argument("--threshold", type=float, default=0.85)

    sub.add_parser("migrate-embedding-cache",
                   help="一次性把嵌入缓存 pkl 迁到 SQLite(之后精筛内存恒定,需内存充裕时跑)")

    pep = sub.add_parser("platform-export-pipeline", help="用平台下载包跑 ERP 图搜、精筛和老板报告")
    pep.add_argument("--platform", default="ixspy")
    pep.add_argument("--source", default="ixspy", choices=["ixspy"])
    pep.add_argument("--product-type", required=True)
    pep.add_argument("--batch", required=True)
    pep.add_argument("--limit", type=int, default=None)
    pep.add_argument("--delay", type=float, default=0.5)
    pep.add_argument("--threshold", type=float, default=0.85)

    pes = sub.add_parser("platform-export-prepare", help="只把平台下载包转成标准化中间 CSV")
    pes.add_argument("--platform", default="ixspy")
    pes.add_argument("--source", default="ixspy", choices=["ixspy"])
    pes.add_argument("--product-type", required=True)
    pes.add_argument("--batch", required=True)

    pef = sub.add_parser("platform-export-finalize", help="基于已有平台导出图搜结果继续精筛并生成最终报告")
    pef.add_argument("--platform", default="ixspy")
    pef.add_argument("--source", default="ixspy", choices=["ixspy"])
    pef.add_argument("--product-type", required=True)
    pef.add_argument("--batch", required=True)
    pef.add_argument("--limit", type=int, default=None)
    pef.add_argument("--threshold", type=float, default=0.85)
    pef.add_argument("--chunk-size", type=int, default=25)

    per = sub.add_parser("platform-export-run",
                         help="一键: 给原始下载文件夹, 自动整理+解析+双筛+出报告(拖拽bat调它)")
    per.add_argument("--src", required=True, help="IXSPY 下载的品类文件夹(含 .xls 和 images)")
    per.add_argument("--limit", type=int, default=None, help="小样本测试用, 如 --limit 30")
    per.add_argument("--delay", type=float, default=0.1)
    per.add_argument("--threshold", type=float, default=0.85)

    iad = sub.add_parser("ixspy-auto",
                         help="一键: 自动登录IXSPY下载该品类压缩包 + 双筛 + 报告")
    iad.add_argument("--category", required=True, help="品类中文名, 如 汽车及零配件")
    iad.add_argument("--headless", action="store_true", help="无界面跑Chrome")
    iad.add_argument("--limit", type=int, default=None, help="小样本测试, 如 --limit 30")
    iad.add_argument("--delay", type=float, default=0.1)
    iad.add_argument("--threshold", type=float, default=0.85)

    args = parser.parse_args()

    if args.command == "ixspy-auto":
        import os
        from sourcing.collect.ixspy_download import download_export, _extract_zip
        from sourcing.platform_export_pipeline import run_from_download, default_base_dir
        base = default_base_dir()
        dl_dir = os.path.join(base, "_downloads", "ixspy")
        print(f"[1/3] 下载品类: {args.category} (会弹Chrome自动登录)")
        zip_path = download_export(args.category, download_dir=dl_dir, headless=args.headless)
        print(f"[2/3] 解压: {zip_path}")
        src = _extract_zip(zip_path, os.path.join(base, "_downloads", "ixspy_extract"))
        print("[3/3] 双筛 + 报告")
        result = run_from_download(src, base_dir=base, category_name=args.category,
                                   limit=args.limit, delay_seconds=args.delay,
                                   threshold=args.threshold)
        report_dir = result.get("report_dir", "")
        print(f"[DONE] {args.category} | 匹配 {result.get('final', {}).get('matched')}"
              f"/{result.get('final', {}).get('products')} | 报告: {report_dir}")
        try:
            os.startfile(report_dir)
        except Exception:
            pass
        return

    if args.command == "platform-export-run":
        from sourcing.platform_export_pipeline import run_from_download
        result = run_from_download(
            args.src, limit=args.limit, delay_seconds=args.delay, threshold=args.threshold)
        auto = result.get("auto", {})
        report_dir = result.get("report_dir", "")
        print(f"[DONE] 品类: {auto.get('product_type_name')} | 批次: {auto.get('batch')} | "
              f"匹配: {result.get('final', {}).get('matched')}/{result.get('final', {}).get('products')}")
        print(f"[报告目录] {report_dir}")
        try:
            import os
            os.startfile(report_dir)  # Windows: 跑完自动打开报告文件夹
        except Exception:
            pass
        return

    if args.command == "migrate-embedding-cache":
        from sourcing.rerank.embed import _import_iem, sqlite_cache_path
        from sourcing.rerank.embed_cache import migrate_pickle_to_sqlite
        _import_iem()
        import image_embedding_matcher as iem
        pkl = iem.EMBEDDING_CACHE_FILE
        sqlite_path = sqlite_cache_path()
        n = migrate_pickle_to_sqlite(pkl, sqlite_path)
        print(f"[DONE] migrated {n} embeddings -> {sqlite_path}")
        return

    if args.command == "platform-export-prepare":
        summary = prepare_standard_input(
            base_dir=config.collect_base_dir(),
            platform=args.platform,
            product_type=args.product_type,
            batch=args.batch,
            source=args.source,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.command == "platform-export-pipeline":
        summary = run_platform_export_pipeline(
            base_dir=config.collect_base_dir(),
            platform=args.platform,
            product_type=args.product_type,
            batch=args.batch,
            source=args.source,
            limit=args.limit,
            delay_seconds=args.delay,
            threshold=args.threshold,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.command == "platform-export-finalize":
        summary = finalize_platform_export_pipeline(
            base_dir=config.collect_base_dir(),
            platform=args.platform,
            product_type=args.product_type,
            batch=args.batch,
            source=args.source,
            threshold=args.threshold,
            limit=args.limit,
            chunk_size=args.chunk_size,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.command == "quality":
        report = inspect_csv_quality(args.path, source=args.source, product_type=args.product_type)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if args.command == "erp-image-search":
        summary = erp_image_search.run_image_search(
            source=args.source,
            product_type=args.product_type,
            base_dir=config.collect_base_dir(),
            limit=args.limit,
            delay_seconds=args.delay,
        )
        print(f"[DONE] ERP image searched: {summary}")
        return

    if args.command == "erp-image-decision-report":
        summary = erp_image_search.generate_boss_decision_report(
            source=args.source,
            product_type=args.product_type,
            base_dir=args.base_dir,
        )
        print(f"[DONE] ERP image decision report: {summary}")
        return

    if args.command == "erp-image-match-report":
        summary = erp_image_search.generate_best_match_report(
            source=args.source, product_type=args.product_type,
            base_dir=args.base_dir or config.collect_base_dir())
        print(f"[DONE] best match report: {summary}")
        return

    if args.command == "erp-image-rerank":
        summary = rerank_image_search(
            source=args.source, product_type=args.product_type,
            base_dir=config.collect_base_dir(), limit=args.limit, threshold=args.threshold)
        print(f"[DONE] reranked: {summary}")
        return

    conn = db.connect(config.database_url())
    try:
        if args.command == "import":
            importers = {
                "seerfar": import_seerfar_csv,
                "ixspy": import_ixspy_csv,
                "erp": import_erp_csv,
            }
            summary = importers[args.source](
                conn, args.path, product_type=args.product_type, source_file=args.path)
            print(f"[DONE] imported: {summary}")
        elif args.command == "analyze":
            summary = run_analysis(conn)
            print(f"[DONE] analyzed: {summary}")
        elif args.command == "collect":
            if args.all:
                targets = config.collect_targets()
            elif args.source and args.product_type:
                targets = [(args.source, args.product_type)]
            else:
                raise SystemExit("collect 需要 --all，或同时给 --source 与 --product-type")
            results = collect_all(conn, targets, base_dir=config.collect_base_dir())
            print(f"[DONE] collected: {results}")
        elif args.command == "bridge-matches":
            summary = bridge_matches(conn, config.app_db_path())
            print(f"[DONE] bridged: {summary}")
        elif args.command == "import-external":
            summary = import_external_products(conn, config.app_db_path())
            print(f"[DONE] imported external: {summary}")
        elif args.command == "erp-image-load-db":
            summary = load_image_decisions(
                conn, source=args.source, product_type=args.product_type,
                base_dir=config.collect_base_dir())
            print(f"[DONE] image decisions loaded: {summary}")
        elif args.command == "erp-image-pipeline":
            summary = run_pipeline(
                conn, source=args.source, product_type=args.product_type,
                base_dir=config.collect_base_dir(), limit=args.limit, threshold=args.threshold)
            print(f"[DONE] pipeline: {summary}")
        elif args.command == "run-product":
            raise SystemExit(_run_product_cli(conn, args))
    finally:
        conn.close()


def _run_product_cli(conn, args) -> int:
    """跑一条龙并写日志文件；返回进程退出码(0 成功 / 1 失败)，供 Windows 计划任务判断。"""
    import datetime
    from pathlib import Path
    from sourcing.run_product import run_product

    base = config.collect_base_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path(base) / "output" / "logs" / args.product_type
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{stamp}.log"
    log_file = open(log_path, "a", encoding="utf-8")

    def emit(message: str) -> None:
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}"
        print(line)
        log_file.write(line + "\n")
        log_file.flush()

    emit(f"[run-product] log -> {log_path}")
    try:
        result = run_product(
            conn, source=args.source, product_type=args.product_type, base_dir=base,
            category=args.category, headless=args.headless or None,
            limit=args.limit, threshold=args.threshold, emit=emit)
    except Exception as error:  # 采集子进程抛错(如类目未选中)也算失败
        emit(f"[run-product] ERROR: {error}")
        log_file.close()
        return 1
    status = result.get("status")
    emit(f"[run-product] DONE status={status}")
    log_file.close()
    return 0 if status == "success" else 1


if __name__ == "__main__":
    main()
