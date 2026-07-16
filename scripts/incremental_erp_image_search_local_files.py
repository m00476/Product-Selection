import argparse
import csv
import mimetypes
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from sourcing import erp_image_search
from sourcing.incremental_search_runtime import run_searches


def existing_external_skus(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(newline="", encoding="utf-8") as file:
        return {row.get("external_sku", "") for row in csv.DictReader(file)}


def _local_search(client: erp_image_search.ErpImageSearchClient, image_path: str):
    path = Path(image_path)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body, boundary = erp_image_search._build_multipart_body(
        fields={"fileUrls": "undefined"},
        files={"files": (path.name, path.read_bytes(), content_type)},
    )
    request = Request(
        client.api_url,
        data=body,
        method="POST",
        headers={
            "Authorization": client.token,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urlopen(request, timeout=client.timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
    except HTTPError as err:
        raw_text = err.read().decode("utf-8", errors="replace")
        try:
            payload = erp_image_search.json.loads(raw_text)
        except erp_image_search.json.JSONDecodeError:
            payload = {"code": err.code, "msg": raw_text[:500], "data": []}
        return erp_image_search.normalize_search_response(payload)
    return erp_image_search.normalize_search_response(erp_image_search.json.loads(raw_text))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--input-csv", default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=1,
                        help="并发上传数；建议先用 2 跑小样本验证 ERP 限流情况")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv) if args.input_csv else erp_image_search.input_csv_path(
        args.base_dir, args.source, args.product_type
    )
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
    client = erp_image_search.ErpImageSearchClient()
    client.url_api_token = ""

    pending = [row for row in rows if row.get("external_sku", "") not in done]

    def search_one(external):
        local_image = (external.get("external_local_image_path") or "").strip()
        if not local_image:
            return erp_image_search.SearchResult(
                status="error", code=None, message="local_image_path is empty", trace_id="", matches=[], raw={}
            )
        return erp_image_search._search_with_retries(
            lambda path: _local_search(client, path),
            local_image,
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
