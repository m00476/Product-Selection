import json
import os
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError

from sourcing.collect.api_common import (
    find_record_lists,
    flatten_product_record,
    product_score,
    read_json,
    request_json,
    write_csv,
    write_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_TYPE = os.environ.get("PRODUCT_TYPE", "xiongzhen").strip() or "xiongzhen"
TARGET_COUNT = int(os.environ.get("ERP_API_TARGET_COUNT") or 0)
MAX_RETRIES = int(os.environ.get("ERP_API_MAX_RETRIES") or 3)
REQUEST_TIMEOUT = int(os.environ.get("ERP_API_TIMEOUT") or 180)
PAGE_SIZE_OVERRIDE = int(os.environ.get("ERP_API_PAGE_SIZE") or 0)
SAVE_RAW_RESPONSE = os.environ.get("ERP_API_SAVE_RAW", "1").lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class ProjectPaths:
    root_dir: Path
    product_type: str

    @property
    def output_dir(self) -> Path:
        return self.root_dir / "output" / "erp" / self.product_type

    @property
    def input_dir(self) -> Path:
        return self.root_dir / "input" / "erp" / self.product_type

    @property
    def candidates_file(self) -> Path:
        return self.output_dir / "erp_api_candidates.json"

    @property
    def raw_response_file(self) -> Path:
        return self.output_dir / "erp_api_response.json"

    @property
    def csv_file(self) -> Path:
        return self.input_dir / "erp_products.csv"

    @property
    def category_config_file(self) -> Path:
        return self.root_dir / "configs" / "erp_categories.yaml"


@dataclass(frozen=True)
class ProductRequest:
    method: str
    url: str
    headers: dict
    body: str


def _parse_scalar(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def load_category_config(path: str | Path):
    config_path = Path(path)
    if not config_path.exists():
        return {}

    data: dict[str, dict] = {}
    current_key = None
    current_list_key = None
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1].strip()
            data[current_key] = {}
            current_list_key = None
            continue
        if current_key is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_list_key:
            data[current_key].setdefault(current_list_key, []).append(_parse_scalar(stripped[2:]))
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                data[current_key][key] = _parse_scalar(value)
                current_list_key = None
            else:
                data[current_key][key] = []
                current_list_key = key
    return data


def apply_category_config(body: str, product_type: str, config: dict) -> dict:
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError:
        payload = {}

    category = (config or {}).get(product_type) or {}
    if not category:
        name = os.environ.get("ERP_CATEGORY_NAME", "")
        return {"body": payload, "expected_categories": [name] if name else []}

    mapping = {
        "first_catalogue_id": "firstcatalogueid",
        "second_catalogue_id": "secondcatalogueid",
        "third_catalogue_id": "thirdcatalogueid",
    }
    for config_key, payload_key in mapping.items():
        value = category.get(config_key)
        if value not in (None, ""):
            payload[payload_key] = str(value)
    payload.setdefault("status", "8")
    payload.setdefault("page", 1)
    payload.setdefault("limit", PAGE_SIZE_OVERRIDE or 100)
    payload.setdefault("isfile", 0)

    accepted = [str(item) for item in category.get("accepted_categories") or [] if item]
    name = category.get("name")
    if name and str(name) not in accepted:
        accepted.append(str(name))
    return {"body": payload, "expected_categories": accepted}


def require_category_request(body: dict, product_type: str, config: dict) -> None:
    category = (config or {}).get(product_type) or {}
    if not category:
        return
    missing = []
    for config_key, payload_key in [
        ("first_catalogue_id", "firstcatalogueid"),
        ("second_catalogue_id", "secondcatalogueid"),
        ("third_catalogue_id", "thirdcatalogueid"),
    ]:
        if category.get(config_key) and not body.get(payload_key):
            missing.append(payload_key)
    if missing:
        raise RuntimeError(
            f"ERP request quality check failed: missing configured category fields {missing} "
            f"for PRODUCT_TYPE={product_type!r}."
        )


def select_candidate(candidates):
    if not candidates:
        raise RuntimeError("No API candidates found. Run ERP probe first or copy erp_api_candidates.json into output/erp/<product_type>.")
    product_candidates = [item for item in candidates if "Api/proudect/list" in item.get("url", "")]
    if product_candidates:
        def candidate_priority(item):
            request = item.get("request") or {}
            post_data = request.get("postData", "") or ""
            try:
                body = json.loads(post_data)
            except json.JSONDecodeError:
                body = {}
            category_score = sum(
                1
                for key in ["firstcatalogueid", "secondcatalogueid", "thirdcatalogueid"]
                if body.get(key)
            )
            page_score = 1 if str(body.get("page", "1")) == "1" else 0
            return (
                category_score,
                page_score,
                item.get("best_record_count", 0),
                item.get("best_product_score", 0),
            )

        return max(product_candidates, key=candidate_priority)
    return max(candidates, key=lambda item: (item.get("best_product_score", 0), item.get("best_record_count", 0)))


def load_product_request(paths: ProjectPaths) -> ProductRequest:
    candidates = read_json(str(paths.candidates_file), default=[])
    candidate = select_candidate(candidates)
    request = deepcopy(candidate.get("request") or {})
    if not request:
        raise RuntimeError("Selected candidate has no replayable request details. Re-run ERP probe.")

    method = request.get("method", "GET")
    url = request.get("url") or candidate["url"]
    headers = request.get("headers", {})
    body = request.get("postData", "")
    if "Api/proudect/list" in url:
        config = load_category_config(paths.category_config_file)
        updated = apply_category_config(body, paths.product_type, config)
        require_category_request(updated["body"], paths.product_type, config)
        body = json.dumps(updated["body"], ensure_ascii=False)
    return ProductRequest(method, url, headers, body)


def extract_best_records(payload):
    lists = find_record_lists(payload)
    if not lists:
        return []
    best = max(lists, key=lambda item: (product_score(item["records"]), len(item["records"])))
    return best["records"]


def first_value(record, keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def flatten_erp_record(record):
    flattened = flatten_product_record(record)
    main_sku = first_value(record, ["mainsku", "mainSku", "main_sku", "parentSku", "parent_sku", "spu"])
    sub_sku = first_value(record, ["sku", "skuid", "subSku", "sub_sku", "productSku"])
    flattened.update(
        {
            "main_sku": main_sku,
            "sub_sku": sub_sku or flattened.get("sku", ""),
            "erp_id": first_value(record, ["id"]),
            "skuid": first_value(record, ["skuid"]),
            "name_cn": first_value(record, ["namecn", "nameCn", "namecnn", "cnName"]),
            "name_en": first_value(record, ["nameen", "nameEn", "enName"]),
            "supplier_name": first_value(record, ["supplyername", "supplyname", "firstsuppliername"]),
            "catalogue_name": first_value(record, ["cataloguename", "cataloguename2"]),
            "pic1": first_value(record, ["pic1"]),
            "pic2": first_value(record, ["pic2"]),
            "pic3": first_value(record, ["pic3"]),
            "cost_price": first_value(record, ["cost_price", "costprice", "costPrice", "costprices"]),
            "weighted_purchase": first_value(record, ["weighted_purchase", "purprice", "npurprice", "initialpurprice"]),
            "weighted_freight": first_value(record, ["weighted_freight", "profreight", "jqfreight"]),
            "weighted_sorting": first_value(record, ["weighted_sorting", "csortingprice", "warehousesortingcost"]),
            "stock": first_value(record, ["stock", "inventory", "stockqty", "stocknum", "totalinventory"]),
            "once_gross_margin": first_value(record, ["once_gross_margin", "oncegrossmargin"]),
            "main_platform": first_value(record, ["main_platform", "salesname"]),
        }
    )
    if not flattened.get("product_name"):
        flattened["product_name"] = flattened["name_cn"] or flattened["name_en"]
    if not flattened.get("image_url"):
        flattened["image_url"] = flattened["pic3"] or flattened["pic1"] or flattened["pic2"]
    if not flattened.get("category"):
        flattened["category"] = flattened["catalogue_name"]
    return flattened


def validate_output_rows(rows, expected_categories=None):
    expected = [str(item).strip() for item in (expected_categories or []) if str(item).strip()]
    if not rows:
        if expected:
            raise RuntimeError(f"ERP output quality check failed: no ERP rows returned for categories {expected!r}.")
        return

    missing_cost = sum(1 for row in rows if not row.get("cost_price"))
    missing_stock = sum(1 for row in rows if not row.get("stock"))
    if missing_cost or missing_stock:
        print(
            f"  [WARN] output quality: {missing_cost}/{len(rows)} rows missing cost_price, "
            f"{missing_stock}/{len(rows)} rows missing stock"
        )

    if not expected:
        return

    matched = sum(
        1
        for row in rows
        if any(category in (row.get("category") or "") for category in expected)
    )
    if matched == 0:
        raise RuntimeError(
            f"ERP output quality check failed: 0/{len(rows)} rows match ERP categories {expected!r}."
        )


def fetch_pages(method, url, headers, body):
    try:
        payload_body = json.loads(body or "{}")
    except json.JSONDecodeError:
        payload_body = {}

    if method.upper() != "POST" or "page" not in payload_body or "limit" not in payload_body:
        payload, response_headers = request_json(method, url, headers=headers, body=body)
        return [payload], response_headers

    all_payloads = []
    response_headers = {}
    page = int(payload_body.get("page") or 1)
    limit = PAGE_SIZE_OVERRIDE or int(payload_body.get("limit") or 100)

    while TARGET_COUNT <= 0 or len(all_payloads) * limit < TARGET_COUNT:
        payload_body["page"] = page
        payload_body["limit"] = limit
        page_body = json.dumps(payload_body, ensure_ascii=False)
        payload = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                payload, response_headers = request_json(
                    method,
                    url,
                    headers=headers,
                    body=page_body,
                    timeout=REQUEST_TIMEOUT,
                )
                break
            except HTTPError as error:
                print(f"  [WARN] page {page} HTTP {error.code}, retry {attempt}/{MAX_RETRIES}")
                if attempt >= MAX_RETRIES:
                    print(f"  [WARN] stopped at page {page}; saving fetched pages")
                    return all_payloads, response_headers
                time.sleep(2 * attempt)
            except (OSError, TimeoutError, IncompleteRead) as error:
                print(f"  [WARN] page {page} request failed ({type(error).__name__}), retry {attempt}/{MAX_RETRIES}")
                if attempt >= MAX_RETRIES:
                    print(f"  [WARN] stopped at page {page}; saving fetched pages")
                    return all_payloads, response_headers
                time.sleep(3 * attempt)
        if payload is None:
            break
        records = extract_best_records(payload)
        if not records:
            break
        if SAVE_RAW_RESPONSE:
            all_payloads.append(payload)
        else:
            all_payloads.append({"records": records})
        print(f"  page {page}: {len(records)} records")
        if len(records) < limit:
            break
        page += 1

    return all_payloads, response_headers


def output_fields():
    return [
        "sku",
        "main_sku",
        "sub_sku",
        "product_name",
        "category",
        "image_url",
        "erp_id",
        "skuid",
        "name_cn",
        "name_en",
        "supplier_name",
        "catalogue_name",
        "cost_price",
        "weighted_purchase",
        "weighted_freight",
        "weighted_sorting",
        "stock",
        "once_gross_margin",
        "main_platform",
        "pic1",
        "pic2",
        "pic3",
    ]


def main():
    paths = ProjectPaths(PROJECT_ROOT, PRODUCT_TYPE)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    request = load_product_request(paths)

    print("=" * 60)
    print("  ERP API Fetch")
    print("=" * 60)
    print(f"[PRODUCT_TYPE] {PRODUCT_TYPE}")
    print(f"[API] {request.method} {request.url}")

    payloads, response_headers = fetch_pages(request.method, request.url, request.headers, request.body)
    write_json(str(paths.raw_response_file), {"headers": response_headers, "payloads": payloads})

    records = []
    for payload in payloads:
        records.extend(extract_best_records(payload))
    if TARGET_COUNT > 0:
        records = records[:TARGET_COUNT]

    rows = []
    for record in records:
        flattened = flatten_erp_record(record)
        if any(flattened.values()):
            rows.append(flattened)

    category_config = load_category_config(paths.category_config_file)
    expected = apply_category_config(request.body, PRODUCT_TYPE, category_config)["expected_categories"]
    validate_output_rows(rows, expected_categories=expected)
    csv_output = write_csv(str(paths.csv_file), rows, fields=output_fields())
    print(f"[DONE] extracted {len(rows)} product-like rows")
    print(f"  raw response: {paths.raw_response_file}")
    print(f"  csv output:   {csv_output}")


if __name__ == "__main__":
    sys.exit(main())
