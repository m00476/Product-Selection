import argparse
from sourcing import config, db
from sourcing.importer import import_seerfar_csv
from sourcing.analysis.run import run_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Sourcing pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="导入源 CSV 到 PostgreSQL")
    imp.add_argument("--source", required=True, choices=["seerfar"])
    imp.add_argument("--path", required=True, help="CSV 文件路径")
    imp.add_argument("--product-type", required=True)

    sub.add_parser("analyze", help="计算利润估算与机会分")

    args = parser.parse_args()
    conn = db.connect(config.database_url())
    try:
        if args.command == "import":
            summary = import_seerfar_csv(
                conn, args.path, product_type=args.product_type, source_file=args.path)
            print(f"[DONE] imported: {summary}")
        elif args.command == "analyze":
            summary = run_analysis(conn)
            print(f"[DONE] analyzed: {summary}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
