import json
import os
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError

from sourcing.collect.api_common import find_record_lists, read_json, request_json, write_csv, write_json


PROJECT_ROOT = Path(os.environ.get("COLLECT_OUTPUT_ROOT") or Path(__file__).resolve().parents[3])
PRODUCT_TYPE = os.environ.get("PRODUCT_TYPE", "xiongzhen").strip() or "xiongzhen"
TARGET_COUNT = int(os.environ.get("SEERFAR_API_TARGET_COUNT") or 0)
PAGE_SIZE = int(os.environ.get("SEERFAR_API_PAGE_SIZE") or 100)
MAX_RETRIES = int(os.environ.get("SEERFAR_API_MAX_RETRIES") or 3)


@dataclass(frozen=True)
class ProjectPaths:
    root_dir: Path
    product_type: str

    @property
    def output_dir(self) -> Path:
        return self.root_dir / "output" / "seerfar" / self.product_type

    @property
    def input_dir(self) -> Path:
        return self.root_dir / "input" / "seerfar" / self.product_type

    @property
    def candidates_file(self) -> Path:
        return self.output_dir / "seerfar_api_candidates.json"

    @property
    def raw_response_file(self) -> Path:
        return self.output_dir / "seerfar_api_response.json"

    @property
    def csv_file(self) -> Path:
        return self.input_dir / "seerfar_products.csv"


@dataclass(frozen=True)
class ProductRequest:
    method: str
    url: str
    headers: dict
    body: str


def select_candidate(candidates):
    if not candidates:
        raise RuntimeError("No API candidates found. Run Seerfar probe first or copy seerfar_api_candidates.json into output/seerfar/<product_type>.")
    product_candidates = [item for item in candidates if "product-report/product/search" in item.get("url", "")]
    if product_candidates:
        return max(product_candidates, key=lambda item: item.get("best_record_count", 0))
    return max(candidates, key=lambda item: (item.get("best_product_score", 0), item.get("best_record_count", 0)))


def load_product_request(paths: ProjectPaths) -> ProductRequest:
    candidates = read_json(str(paths.candidates_file), default=[])
    candidate = select_candidate(candidates)
    request = deepcopy(candidate.get("request") or {})
    if not request:
        raise RuntimeError("Selected Seerfar candidate has no replayable request details. Re-run probe.")
    method = request.get("method", "GET")
    url = request.get("url") or candidate["url"]
    headers = request.get("headers", {})
    body = request.get("postData", "")
    return ProductRequest(method, url, headers, body)


def extract_best_records(payload):
    lists = find_record_lists(payload)
    if not lists:
        return []
    return max(lists, key=lambda item: len(item["records"]))["records"]


def category_text(record):
    category = ((record.get("categoryInfo") or {}).get("category") or {})
    path = (record.get("categoryInfo") or {}).get("cnTitlePath") or ""
    en_path = (record.get("categoryInfo") or {}).get("enTitlePath") or ""
    title = category.get("cnTitle") or category.get("title") or category.get("enTitle") or ""
    if path and en_path:
        return f"{path} > {en_path}"
    return path or en_path or title


def clean_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def flatten_seerfar_record(record, source_rank=None):
    category_info = record.get("categoryInfo") or {}
    category = category_info.get("category") or {}
    return {
        "source_rank": source_rank if source_rank is not None else "",
        "sku": clean_value(record.get("sku")),
        "product_name": str(record.get("title") or ""),
        "brand": str(record.get("brandName") or ""),
        "category": category_text(record),
        "image_url": str(record.get("imageUrl") or ""),
        "product_url": clean_value(record.get("productUrl")),
        "price": clean_value(record.get("price")),
        "seller_id": clean_value(record.get("sellerId")),
        "seller_name": clean_value(record.get("sellerName")),
        "brand_id": clean_value(record.get("brandId")),
        "brand_url": clean_value(record.get("brandUrl")),
        "sales": clean_value(record.get("sales")),
        "origin_sales": clean_value(record.get("originSales")),
        "sales_rate": clean_value(record.get("salesRate")),
        "revenue": clean_value(record.get("revenue")),
        "revenue_rate": clean_value(record.get("revenueRate")),
        "review_count": clean_value(record.get("reviewCount")),
        "review_rating": clean_value(record.get("reviewRating")),
        "questions_and_answers": clean_value(record.get("questionsAndAnswers")),
        "up_days": clean_value(record.get("upDays")),
        "up_months": clean_value(record.get("upMonths")),
        "weight": clean_value(record.get("weight")),
        "dimension": clean_value(record.get("dimension")),
        "volume": clean_value(record.get("volume")),
        "variants": clean_value(record.get("variants")),
        "variation_ids": clean_value(record.get("variationIds")),
        "category_id": clean_value(category.get("id")),
        "category_cn_title": clean_value(category.get("cnTitle")),
        "category_en_title": clean_value(category.get("enTitle")),
        "category_title": clean_value(category.get("title")),
        "fulfillment": clean_value(record.get("fulfillment")),
        "labels": clean_value(record.get("labels")),
        "raw_json": clean_value(record),
    }


def validate_output_rows(rows):
    if not rows:
        raise RuntimeError("Seerfar output quality check failed: no product rows were fetched.")
    missing_identity = sum(1 for row in rows if not (row.get("sku") or row.get("product_url")))
    missing_payload = sum(1 for row in rows if not (row.get("product_name") or row.get("image_url")))
    if missing_identity == len(rows) and missing_payload == len(rows):
        raise RuntimeError("Seerfar output quality check failed: all rows are missing identity and product details.")
    missing_price = sum(1 for row in rows if not row.get("price"))
    missing_sales = sum(1 for row in rows if not (row.get("sales") or row.get("origin_sales")))
    if missing_price or missing_sales:
        print(
            f"  [WARN] output quality: {missing_price}/{len(rows)} rows missing price, "
            f"{missing_sales}/{len(rows)} rows missing sales"
        )


def fetch_pages(method, url, headers, body):
    try:
        payload_body = json.loads(body or "{}")
    except json.JSONDecodeError:
        payload_body = {}

    page_config = payload_body.get("page")
    if method.upper() != "POST" or not isinstance(page_config, dict):
        payload, response_headers = request_json(method, url, headers=headers, body=body)
        return [payload], response_headers

    all_payloads = []
    response_headers = {}
    page_number = int(page_config.get("pageNumber") or 1)
    page_size = PAGE_SIZE or int(page_config.get("pageSize") or 20)

    while TARGET_COUNT <= 0 or len(all_payloads) * page_size < TARGET_COUNT:
        payload_body["page"]["pageNumber"] = page_number
        payload_body["page"]["pageSize"] = page_size
        page_body = json.dumps(payload_body, ensure_ascii=False)
        payload = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                payload, response_headers = request_json(method, url, headers=headers, body=page_body, timeout=120)
                break
            except HTTPError as error:
                print(f"  [WARN] stopped at page {page_number}: HTTP {error.code}")
                return all_payloads, response_headers
            except (OSError, TimeoutError, IncompleteRead, URLError) as error:
                print(f"  [WARN] page {page_number} attempt {attempt}/{MAX_RETRIES} failed: {error}")
                if attempt == MAX_RETRIES:
                    print(f"  [WARN] keeping {len(all_payloads)} completed pages and stopping")
                    return all_payloads, response_headers
                time.sleep(2 * attempt)
        if payload is None:
            break
        records = extract_best_records(payload)
        if not records:
            break
        all_payloads.append(payload)
        print(f"  page {page_number}: {len(records)} records")
        if len(records) < page_size:
            break
        page_number += 1

    return all_payloads, response_headers


def output_fields():
    return [
        "source_rank", "sku", "product_name", "brand", "category", "image_url",
        "product_url", "price", "seller_id", "seller_name", "brand_id", "brand_url",
        "sales", "origin_sales", "sales_rate", "revenue", "revenue_rate",
        "review_count", "review_rating", "questions_and_answers", "up_days",
        "up_months", "weight", "dimension", "volume", "variants", "variation_ids",
        "category_id", "category_cn_title", "category_en_title", "category_title",
        "fulfillment", "labels", "raw_json",
    ]


def main():
    paths = ProjectPaths(PROJECT_ROOT, PRODUCT_TYPE)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    request = load_product_request(paths)

    print("=" * 60)
    print("  Seerfar API Fetch")
    print("=" * 60)
    print(f"[PRODUCT_TYPE] {PRODUCT_TYPE}")
    print(f"[API] {request.method} {request.url}")

    payloads, response_headers = fetch_pages(request.method, request.url, request.headers, request.body)
    records = []
    for payload in payloads:
        records.extend(extract_best_records(payload))
    if TARGET_COUNT > 0:
        records = records[:TARGET_COUNT]
    rows = [flatten_seerfar_record(record, index + 1) for index, record in enumerate(records)]

    validate_output_rows(rows)
    write_json(str(paths.raw_response_file), {"headers": response_headers, "payloads": payloads})
    csv_output = write_csv(str(paths.csv_file), rows, fields=output_fields())
    print(f"[DONE] extracted {len(rows)} product-like rows")
    print(f"  raw response: {paths.raw_response_file}")
    print(f"  csv output:   {csv_output}")


if __name__ == "__main__":
    sys.exit(main())
