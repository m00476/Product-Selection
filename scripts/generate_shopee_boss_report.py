import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from sourcing import erp_image_search as e
from sourcing.shopee_boss_report import SHOPEE_BOSS_REPORT_FIELDS, build_shopee_boss_report_rows


csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成保留 Shopee 原字段的老板版报告")
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()

    source_rows = e._read_csv_dicts(args.input_csv)
    match_rows = e._read_csv_dicts(e.output_csv_path(args.base_dir, "seerfar", args.product_type))
    rows = build_shopee_boss_report_rows(source_rows, match_rows)

    output_dir = Path(args.base_dir) / "output" / "image_search" / "shopee" / args.product_type
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / "shopee_boss_report.csv"
    xlsx_path = output_dir / f"Shopee_房屋与建筑_老板版报告_{timestamp}.xlsx"
    frame = pd.DataFrame(rows, columns=SHOPEE_BOSS_REPORT_FIELDS)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    frame.to_excel(xlsx_path, index=False)
    print(
        {
            "rows": len(rows),
            "verdicts": frame["匹配判定"].value_counts().to_dict() if not frame.empty else {},
            "csv": str(csv_path),
            "xlsx": str(xlsx_path),
        }
    )


if __name__ == "__main__":
    main()
