import argparse
import json
from sourcing import config, db
from sourcing.importer import import_erp_csv, import_ixspy_csv, import_seerfar_csv
from sourcing.analysis.run import run_analysis
from sourcing.quality import inspect_csv_quality


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
    finally:
        conn.close()


if __name__ == "__main__":
    main()
