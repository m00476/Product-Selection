import argparse
from sourcing import config, db
from sourcing.importer import import_seerfar_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Import source CSV into PostgreSQL")
    parser.add_argument("--source", required=True, choices=["seerfar"])
    parser.add_argument("--path", required=True, help="CSV 文件路径")
    parser.add_argument("--product-type", required=True)
    args = parser.parse_args()

    conn = db.connect(config.database_url())
    try:
        if args.source == "seerfar":
            summary = import_seerfar_csv(
                conn, args.path, product_type=args.product_type, source_file=args.path)
        print(f"[DONE] imported: {summary}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
