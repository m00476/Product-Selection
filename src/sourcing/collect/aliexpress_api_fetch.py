import json
import os
import re
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError

from sourcing.collect.api_common import find_record_lists, read_json, request_json, write_csv, write_json


PROJECT_ROOT = Path(os.environ.get("COLLECT_OUTPUT_ROOT") or Path(__file__).resolve().parents[3])
PRODUCT_TYPE = os.environ.get("PRODUCT_TYPE", "furniture").strip() or "furniture"
ALIEXPRESS_CATEGORY_NAME = os.environ.get("ALIEXPRESS_CATEGORY_NAME", os.environ.get("IXSPY_CATEGORY_NAME", ""))
TARGET_COUNT = int(os.environ.get("ALIEXPRESS_API_TARGET_COUNT") or 0)
PAGE_SIZE = int(os.environ.get("ALIEXPRESS_API_PAGE_SIZE") or 100)
MAX_RETRIES = int(os.environ.get("ALIEXPRESS_API_MAX_RETRIES") or 3)


@dataclass(frozen=True)
class ProjectPaths:
    root_dir: Path
    product_type: str

    @property
    def output_dir(self) -> Path:
        return self.root_dir / "output" / "aliexpress" / self.product_type

    @property
    def input_dir(self) -> Path:
        return self.root_dir / "input" / "aliexpress" / self.product_type

    @property
    def candidates_file(self) -> Path:
        return self.output_dir / "aliexpress_api_candidates.json"

    @property
    def raw_response_file(self) -> Path:
        return self.output_dir / "aliexpress_api_response.json"

    @property
    def csv_file(self) -> Path:
        return self.input_dir / "aliexpress_products.csv"


@dataclass(frozen=True)
class ProductRequest:
    method: str
    url: str
    headers: dict
    body: str


def first_value(record, keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            if isinstance(value, list):
                return ",".join(str(item) for item in value)
            return str(value).strip()
    return ""


def nested_first_value(record, paths):
    for path in paths:
        value = record
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_epoch_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{10,13}", text):
        timestamp = int(text)
        if len(text) == 13:
            timestamp = timestamp // 1000
        return time.strftime("%Y-%m-%d", time.localtime(timestamp))
    return text


def numeric_value(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    units = {"万": 10000, "千": 1000, "k": 1000, "K": 1000}
    multiplier = 1
    if text[-1:] in units:
        multiplier = units[text[-1]]
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def avg_daily_sales_1y(value):
    number = numeric_value(value)
    if number is None:
        return ""
    return str(int(round(number / 365)))


def fulfillment_type(record):
    explicit = first_value(
        record,
        ["fulfillment_type", "fulfillmentType", "managed_type", "managedType", "choiceName", "choice_name"],
    )
    if explicit:
        return explicit

    choice = first_value(record, ["choice"])
    choice_type = first_value(record, ["choice_type", "choiceType"])
    if choice == "0" and choice_type == "0":
        return "非托管"
    if choice_type == "1":
        return "全托管"
    if choice_type == "2":
        return "半托管"
    if choice == "1":
        return "托管"
    return ""


def flatten_aliexpress_record(record, source_rank=None):
    if not isinstance(record, dict):
        return {}
    product_url = first_value(
        record,
        ["product_url", "productUrl", "productLink", "itemUrl", "goodsUrl", "url", "detailUrl", "pcDetailUrl"],
    )
    sku = first_value(
        record,
        ["sku", "productId", "product_id", "itemId", "item_id", "goodsId", "goods_id", "id"],
    )
    if not sku and product_url:
        match = re.search(r"/item/(\d+)\.html", product_url)
        if match:
            sku = match.group(1)
    if sku and not product_url and re.fullmatch(r"\d{8,}", sku):
        product_url = f"https://www.aliexpress.com/item/{sku}.html"

    category = first_value(
        record,
        [
            "category",
            "categoryName",
            "category_name",
            "categoryPath",
            "category_path",
            "category_id",
            "cateName",
            "cnTitlePath",
            "enTitlePath",
        ],
    )
    if not category:
        category = nested_first_value(record, [["categoryInfo", "cnTitlePath"], ["categoryInfo", "enTitlePath"]])

    sales_1y = first_value(record, ["sales_1y", "sales1y", "trade_total", "tradeTotal", "sales", "order_count", "orders"])
    comments_1y = first_value(record, ["comments_1y", "comments1y", "review_total", "reviewTotal", "review_count", "reviews"])
    first_found_at = normalize_epoch_date(
        first_value(record, ["first_found_at", "firstFoundAt", "first_found_time", "firstFoundTime", "add_time", "addTime"])
    )
    daily_sales_1y = first_value(
        record,
        ["avg_daily_sales_1y", "average_daily_sales_1y", "daily_sales_1y", "trade_avg_day", "tradeAvgDay"],
    ) or avg_daily_sales_1y(sales_1y)
    weekly_growth = first_value(record, ["weekly_growth", "week_growth", "trade_inc", "tradeInc", "growth_7d"])

    return {
        "source_rank": source_rank if source_rank is not None else first_value(record, ["rank_num", "rank", "ranking", "index"]),
        "sku": sku,
        "product_name": first_value(
            record,
            ["product_name", "productName", "productTitle", "title", "name", "goodsName", "itemTitle", "subject"],
        ),
        "brand": first_value(record, ["brand", "brandName", "brand_name", "shopName", "storeName"]),
        "category": ALIEXPRESS_CATEGORY_NAME or category,
        "image_url": first_value(
            record,
            [
                "image_url",
                "imageUrl",
                "image",
                "mainImage",
                "mainImg",
                "imgUrl",
                "picUrl",
                "url_image",
                "productImage",
                "product_image",
            ],
        ),
        "price": first_value(record, ["price", "salePrice", "productPrice", "product_price", "minPrice", "amount"]),
        "product_url": product_url,
        "sales": sales_1y,
        "sales_1y": sales_1y,
        "sales_7d": first_value(record, ["sales_7d", "trade_7_count", "trade7Count", "recent_sales"]),
        "review_count": comments_1y,
        "comments_1y": comments_1y,
        "rating": first_value(record, ["rating", "ratings", "review_rating", "reviewRating"]),
        "seller_id": first_value(record, ["seller_id", "store_id", "storeId", "shopId"]),
        "seller_name": first_value(record, ["seller_name", "store_name", "storeName", "shopName"]),
        "seller_positive_rate": nested_first_value(record, [["feedback", "positive_rate"]]),
        "weekly_growth": weekly_growth,
        "first_found_at": first_found_at,
        "avg_daily_sales_1y": daily_sales_1y,
        "fulfillment_type": fulfillment_type(record),
        "choice": first_value(record, ["choice"]),
        "choice_type": first_value(record, ["choice_type", "choiceType"]),
    }


def validate_output_rows(rows):
    if not rows:
        raise RuntimeError("AliExpress output quality check failed: no product rows were fetched.")

    missing_identity = sum(1 for row in rows if not (row.get("sku") or row.get("product_url")))
    missing_price = sum(1 for row in rows if not row.get("price"))
    if missing_identity == len(rows) and missing_price == len(rows):
        raise RuntimeError(
            "AliExpress output quality check failed: all rows are missing sku/product_url/price. "
            "Run AliExpress probe and select a captured API candidate instead of a visible-page fallback."
        )

    if missing_identity or missing_price:
        print(
            f"  [WARN] output quality: {missing_identity}/{len(rows)} rows missing sku/product_url, "
            f"{missing_price}/{len(rows)} rows missing price"
        )


def select_candidate(candidates):
    if not candidates:
        raise RuntimeError("No API candidates found. Run AliExpress probe first or copy aliexpress_api_candidates.json into output/aliexpress/<product_type>.")
    keyword_candidates = [
        item
        for item in candidates
        if any(token in item.get("url", "").lower() for token in ["product", "goods", "item"])
    ]
    if keyword_candidates:
        return max(keyword_candidates, key=lambda item: (item.get("best_product_score", 0), item.get("best_record_count", 0)))
    return max(candidates, key=lambda item: (item.get("best_product_score", 0), item.get("best_record_count", 0)))


def load_product_request(paths: ProjectPaths) -> ProductRequest:
    candidates = read_json(str(paths.candidates_file), default=[])
    candidate = select_candidate(candidates)
    request = deepcopy(candidate.get("request") or {})
    if not request:
        raise RuntimeError("Selected AliExpress candidate has no replayable request details. Re-run probe.")
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


def set_if_present(container, keys, value):
    for key in keys:
        if isinstance(container, dict) and key in container:
            container[key] = value
            return True
    return False


def apply_page(body, page_number, page_size):
    changed = False
    if isinstance(body.get("page"), dict):
        changed = set_if_present(body["page"], ["pageNumber", "pageNo", "pageNum", "current", "page"], page_number) or changed
        changed = set_if_present(body["page"], ["pageSize", "size", "limit"], page_size) or changed
    changed = set_if_present(body, ["pageNumber", "pageNo", "pageNum", "current", "page"], page_number) or changed
    changed = set_if_present(body, ["pageSize", "size", "limit"], page_size) or changed
    return changed


def fetch_pages(method, url, headers, body):
    try:
        payload_body = json.loads(body or "{}")
    except json.JSONDecodeError:
        payload_body = {}

    if method.upper() != "POST" or not isinstance(payload_body, dict):
        payload, response_headers = request_json(method, url, headers=headers, body=body)
        return [payload], response_headers

    page_number = 1
    page_size = PAGE_SIZE
    all_payloads = []
    response_headers = {}
    if not apply_page(payload_body, page_number, page_size):
        payload, response_headers = request_json(method, url, headers=headers, body=body)
        return [payload], response_headers

    while TARGET_COUNT <= 0 or len(all_payloads) * page_size < TARGET_COUNT:
        apply_page(payload_body, page_number, page_size)
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
        "price", "product_url", "sales", "sales_1y", "sales_7d", "review_count",
        "comments_1y", "rating", "weekly_growth", "first_found_at", "avg_daily_sales_1y",
        "fulfillment_type", "choice", "choice_type", "seller_id", "seller_name",
        "seller_positive_rate",
    ]


def main():
    paths = ProjectPaths(PROJECT_ROOT, PRODUCT_TYPE)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    request = load_product_request(paths)

    print("=" * 60)
    print("  AliExpress IXSPY API Fetch")
    print("=" * 60)
    print(f"[PRODUCT_TYPE] {PRODUCT_TYPE}")
    print(f"[API] {request.method} {request.url}")

    payloads, response_headers = fetch_pages(request.method, request.url, request.headers, request.body)
    records = []
    for payload in payloads:
        records.extend(extract_best_records(payload))
    if TARGET_COUNT > 0:
        records = records[:TARGET_COUNT]

    rows = []
    seen = set()
    for index, record in enumerate(records, start=1):
        row = flatten_aliexpress_record(record, index)
        if not any(row.values()):
            continue
        key = row.get("sku") or row.get("product_url") or row.get("image_url") or f"row-{index}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    validate_output_rows(rows)
    write_json(str(paths.raw_response_file), {"headers": response_headers, "payloads": payloads})
    csv_output = write_csv(str(paths.csv_file), rows, fields=output_fields())
    print(f"[DONE] extracted {len(rows)} product-like rows")
    print(f"  raw response: {paths.raw_response_file}")
    print(f"  csv output:   {csv_output}")


if __name__ == "__main__":
    sys.exit(main())
