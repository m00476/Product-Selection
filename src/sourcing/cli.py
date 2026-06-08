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

    args = parser.parse_args()

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
    finally:
        conn.close()


if __name__ == "__main__":
    main()
