import argparse
import json
from sourcing import config, db
from sourcing.importer import import_erp_csv, import_ixspy_csv, import_seerfar_csv
from sourcing.analysis.run import run_analysis
from sourcing.quality import inspect_csv_quality
from sourcing.collect.orchestrator import collect_all
from sourcing.bridge.run import bridge_matches


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

    args = parser.parse_args()

    if args.command == "quality":
        report = inspect_csv_quality(args.path, source=args.source, product_type=args.product_type)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
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
    finally:
        conn.close()


if __name__ == "__main__":
    main()
