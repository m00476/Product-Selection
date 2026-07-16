import argparse
import csv
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from sourcing import erp_image_search
from sourcing.incremental_search_runtime import run_searches


def existing_external_skus(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(newline="", encoding="utf-8") as file:
        return {row.get("external_sku", "") for row in csv.DictReader(file)}


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=1,
                        help="并发请求数；建议先用 2 跑小样本验证 ERP 限流情况")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_path = erp_image_search.input_csv_path(args.base_dir, args.source, args.product_type)
    output_path = erp_image_search.output_csv_path(args.base_dir, args.source, args.product_type)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.overwrite and output_path.exists():
        output_path.unlink()

    rows = erp_image_search.load_external_rows(input_path, source=args.source, product_type=args.product_type)
    if args.limit is not None:
        rows = rows[: args.limit]

    done = existing_external_skus(output_path)
    fieldnames = erp_image_search.RESULT_FIELDS
    write_header = not output_path.exists() or output_path.stat().st_size == 0
    client = erp_image_search.ErpImageSearchClient(top_n=args.top_n)
    refresh_lock = threading.Lock()
    refreshed = False

    pending = [row for row in rows if row.get("external_sku", "") not in done]

    def search_one(external):
        nonlocal refreshed
        result = erp_image_search._search_with_retries(
            client.search,
            external["external_image_url"],
            max_retries=3,
            sleep_func=time.sleep,
        )
        if not erp_image_search._is_auth_failure(result):
            return result

        with refresh_lock:
            if not refreshed:
                erp_image_search.refresh_image_search_client_token(client)
                refreshed = True
        return erp_image_search._search_with_retries(
            client.search,
            external["external_image_url"],
            max_retries=3,
            sleep_func=time.sleep,
        )

    searched = 0
    written = 0
    with output_path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for index, external, result in run_searches(
            pending,
            search_one,
            workers=args.workers,
            delay_seconds=args.delay,
        ):
            sku = external.get("external_sku", "")
            result_rows = erp_image_search._result_rows(external, result)
            writer.writerows(result_rows)
            file.flush()
            searched += 1
            written += len(result_rows)
            done.add(sku)
            if searched % 25 == 0:
                print(f"processed={searched} total_index={index} written={written}", flush=True)

    print({
        "source": args.source,
        "product_type": args.product_type,
        "input": str(input_path),
        "output": str(output_path),
        "searched": searched,
        "written": written,
        "skipped_existing": len(rows) - len(pending),
    })


if __name__ == "__main__":
    main()
