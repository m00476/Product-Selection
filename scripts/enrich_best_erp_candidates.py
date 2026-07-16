import argparse
import csv
import sys

from sourcing import erp_image_search as e
from sourcing.collect.api_common import write_csv


KEEP_VERDICTS = {"高置信匹配", "可能匹配"}
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="补充可用匹配的 ERP 子 SKU 库存、销量和状态")
    parser.add_argument("--source", required=True)
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()

    path = e.output_csv_path(args.base_dir, args.source, args.product_type)
    rows = e._read_csv_dicts(path)
    best_indexes: dict[str, int] = {}
    for index, row in enumerate(rows):
        sku = (row.get("external_sku") or "").strip()
        if not sku or not (row.get("matched_main_sku") or "").strip():
            continue
        if e.best_match_verdict(e._embedding_value(row)) not in KEEP_VERDICTS:
            continue
        current = best_indexes.get(sku)
        if current is None or e._embedding_value(row) > e._embedding_value(rows[current]):
            best_indexes[sku] = index

    client = e.ErpSubSkuClient(timeout=60)
    enriched_count = 0
    error_count = 0
    for index in best_indexes.values():
        enriched = e.enrich_matches_with_sub_skus([rows[index]], client.fetch)[0]
        rows[index] = enriched
        enriched_count += 1
        error_count += int(bool(enriched.get("erp_subsku_error")))

    output = write_csv(str(path), rows, e._fields_with_extras(list(e.RESULT_FIELDS), rows))
    print({"enriched": enriched_count, "errors": error_count, "output": output})


if __name__ == "__main__":
    main()
