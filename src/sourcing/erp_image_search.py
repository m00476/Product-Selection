import csv
import json
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sourcing.collect.api_common import write_csv


DEFAULT_API_URL = "http://103.198.125.2:8077/Api/prodetail/picSearchFunds"
DEFAULT_MULTI_URL_API_URL = "http://103.198.125.2:16777/open/pic/searchProductsByPicUrl"
DEFAULT_URL_API_URL = "http://103.198.125.2:16777/open/pic/searchProductByPicUrl"
DEFAULT_SUB_SKU_API_URL = "http://103.198.125.2:8077/Api/progroup/findSonSku"
DEFAULT_PRODUCT_LIST_API_URL = "http://103.198.125.2:8077/Api/proudect/list"
RESULT_FIELDS = [
    "source",
    "product_type",
    "external_sku",
    "external_product_name",
    "external_product_url",
    "external_image_url",
    "external_source_rank",
    "external_brand",
    "external_category",
    "external_price",
    "external_sales",
    "external_sales_1y",
    "external_sales_7d",
    "external_review_count",
    "external_comments_1y",
    "external_rating",
    "external_weekly_growth",
    "external_first_found_at",
    "external_avg_daily_sales_1y",
    "external_fulfillment_type",
    "external_choice",
    "external_choice_type",
    "external_seller_id",
    "external_seller_name",
    "external_seller_positive_rate",
    "match_status",
    "match_rank",
    "match_source",
    "matched_erp_sku",
    "matched_main_sku",
    "erp_product_status",
    "erp_product_status_text",
    "candidate_priority",
    "erp_image_url",
    "similarity",
    "erp_subsku_count",
    "erp_total_inventory",
    "erp_cost_price",
    "erp_sell_price",
    "erp_sales_num",
    "erp_subsku_json",
    "message",
    "code",
    "trace_id",
    "searched_at",
    "raw_json",
]

BOSS_DECISION_FIELDS = [
    "source",
    "product_type",
    "external_sku",
    "external_product_name",
    "external_product_url",
    "external_image_url",
    "external_source_rank",
    "external_brand",
    "external_category",
    "external_price",
    "external_sales",
    "external_sales_1y",
    "external_sales_7d",
    "external_review_count",
    "external_comments_1y",
    "external_rating",
    "external_weekly_growth",
    "external_first_found_at",
    "external_avg_daily_sales_1y",
    "external_fulfillment_type",
    "external_choice",
    "external_choice_type",
    "external_seller_id",
    "external_seller_name",
    "external_seller_positive_rate",
    "final_decision",
    "boss_action",
    "candidate_count",
    "normal_candidate_count",
    "stopped_candidate_count",
    "limited_candidate_count",
    "risk_candidate_count",
    "top_erp_skus",
    "top_main_skus",
    "max_embedding_similarity",
]

BOSS_DECISION_FIELD_LABELS = {
    "source": "数据来源",
    "product_type": "商品类型",
    "external_sku": "外部平台SKU",
    "external_product_name": "外部平台商品标题",
    "external_product_url": "外部平台商品链接",
    "external_image_url": "外部平台主图链接",
    "external_source_rank": "外部平台排序",
    "external_brand": "外部平台品牌",
    "external_category": "外部平台类目",
    "external_price": "外部平台价格",
    "external_sales": "外部平台累计销量",
    "external_sales_1y": "近一年销量",
    "external_sales_7d": "近7天销量",
    "external_review_count": "外部平台评论数",
    "external_comments_1y": "近一年评论数",
    "external_rating": "外部平台评分",
    "external_weekly_growth": "周增长数",
    "external_first_found_at": "首次发现时间",
    "external_avg_daily_sales_1y": "近一年日均销量",
    "external_fulfillment_type": "托管类型",
    "external_choice": "托管标记",
    "external_choice_type": "托管类型原始值",
    "external_seller_id": "外部平台卖家ID",
    "external_seller_name": "外部平台卖家名称",
    "external_seller_positive_rate": "外部平台卖家好评率",
    "final_decision": "系统判断",
    "boss_action": "建议动作",
    "candidate_count": "ERP候选数量",
    "normal_candidate_count": "ERP正常同款数量",
    "stopped_candidate_count": "ERP停产同款数量",
    "limited_candidate_count": "ERP采购受限同款数量",
    "risk_candidate_count": "ERP风险同款数量",
    "top_erp_skus": "最相似ERP SKU",
    "top_main_skus": "对应ERP主SKU",
    "max_embedding_similarity": "最高图片相似度",
}

PRODUCT_STATUS_MAP = {
    "1": "停产商品",
    "2": "清仓商品",
    "4": "侵权风险商品",
    "5": "站点违规风险商品",
    "6": "采购不到商品",
    "7": "自动创建",
    "8": "正常商品",
    "9": "质量差商品",
    "10": "暂时采购不到商品",
    "11": "禁运产品",
    "12": "GBC侵权",
    "13": "疑似侵权",
    "14": "违禁品商品",
}


@dataclass
class SearchResult:
    status: str
    code: int | None
    message: str
    trace_id: str
    matches: list[dict]
    raw: dict


class ErpImageSearchClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str | None = None,
        top_n: int | None = None,
        timeout: int = 60,
    ) -> None:
        self.token = token if token is not None else os.environ.get("ERP_IMAGE_SEARCH_TOKEN", "")
        self.url_api_token = os.environ.get("ERP_IMAGE_SEARCH_BY_URL_TOKEN", "")
        self.url_api_url = os.environ.get("ERP_IMAGE_SEARCH_BY_URL_URL", DEFAULT_MULTI_URL_API_URL)
        self.legacy_url_api_url = os.environ.get("ERP_IMAGE_SEARCH_BY_URL_LEGACY_URL", DEFAULT_URL_API_URL)
        if not self.token and not self.url_api_token:
            raise RuntimeError("ERP_IMAGE_SEARCH_TOKEN not set")
        self.api_url = api_url or os.environ.get("ERP_IMAGE_SEARCH_URL", DEFAULT_API_URL)
        self.top_n = top_n if top_n is not None else int(os.environ.get("ERP_IMAGE_SEARCH_TOP_N", "10") or "10")
        self.timeout = timeout

    def search(self, image_url: str) -> SearchResult:
        if self.url_api_token:
            return self._search_by_url(image_url)
        image_bytes, filename, content_type = self._download_image(image_url)
        body, boundary = _build_multipart_body(
            fields={"fileUrls": "undefined"},
            files={"files": (filename, image_bytes, content_type)},
        )
        request = Request(
            self.api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": self.token,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as err:
            raw_text = err.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = {"code": err.code, "msg": raw_text[:500], "data": []}
            return normalize_search_response(payload)

        return normalize_search_response(json.loads(raw_text))

    def _search_by_url(self, image_url: str) -> SearchResult:
        if not image_url or not image_url.lower().startswith(("http://", "https://")):
            raise RuntimeError("external image_url must start with http:// or https://")
        body = json.dumps(build_url_search_body(image_url, self.top_n), ensure_ascii=False).encode("utf-8")
        request = Request(
            build_url_search_request_url(self.url_api_url or DEFAULT_MULTI_URL_API_URL, self.top_n),
            data=body,
            method="POST",
            headers={
                "Authorization": self.url_api_token,
                "Content-Type": "application/json;charset=UTF-8",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as err:
            raw_text = err.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = {"code": err.code, "msg": raw_text[:500], "data": []}
            result = normalize_search_response(payload)
            if self.legacy_url_api_url and self.legacy_url_api_url != (self.url_api_url or DEFAULT_MULTI_URL_API_URL):
                return self._search_by_legacy_url(image_url)
            return result

        return normalize_search_response(json.loads(raw_text))

    def _search_by_legacy_url(self, image_url: str) -> SearchResult:
        body = json.dumps(build_url_search_body(image_url, self.top_n), ensure_ascii=False).encode("utf-8")
        request = Request(
            build_url_search_request_url(self.legacy_url_api_url, self.top_n),
            data=body,
            method="POST",
            headers={
                "Authorization": self.url_api_token,
                "Content-Type": "application/json;charset=UTF-8",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as err:
            raw_text = err.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = {"code": err.code, "msg": raw_text[:500], "data": []}
            return normalize_search_response(payload)

        return normalize_search_response(json.loads(raw_text))

    def _download_image(self, image_url: str) -> tuple[bytes, str, str]:
        if not image_url or not image_url.lower().startswith(("http://", "https://")):
            raise RuntimeError("external image_url must start with http:// or https://")
        request = Request(image_url, headers={"User-Agent": "ProductSourcingSystem/0.1"})
        with urlopen(request, timeout=self.timeout) as response:
            data = response.read()
            content_type = response.headers.get_content_type() or "image/jpeg"
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        return data, f"erp-search-image{extension}", content_type


class ErpSubSkuClient:
    def __init__(self, *, token: str | None = None, api_url: str | None = None, timeout: int = 60) -> None:
        self.token = token if token is not None else os.environ.get("ERP_IMAGE_SEARCH_TOKEN", "")
        self.login_token = ""
        self.login_api_url = os.environ.get("ERP_LOGIN_URL", "http://103.198.125.2:8077/newIp/system/login")
        self.login_username = os.environ.get("ERP_USERNAME", os.environ.get("ERP_LOGIN_USERNAME", ""))
        self.login_password = os.environ.get("ERP_PASSWORD", os.environ.get("ERP_LOGIN_PASSWORD", ""))
        if not self.token and not (self.login_username and self.login_password):
            raise RuntimeError("ERP_IMAGE_SEARCH_TOKEN or ERP_USERNAME/ERP_PASSWORD not set")
        self.api_url = api_url or os.environ.get("ERP_SUB_SKU_URL", DEFAULT_SUB_SKU_API_URL)
        self.product_list_api_url = os.environ.get("ERP_PRODUCT_LIST_URL", DEFAULT_PRODUCT_LIST_API_URL)
        self.timeout = timeout

    def fetch(self, main_sku: str) -> list[dict]:
        records = self._fetch_find_son_sku(main_sku)
        product_list = self._fetch_product_list(main_sku)
        if records:
            return merge_product_list_details(records, product_list)
        return product_list

    def _fetch_find_son_sku(self, main_sku: str) -> list[dict]:
        body = json.dumps({"mainsku": main_sku, "mainSku": main_sku}, ensure_ascii=False).encode("utf-8")
        token = self._authorization_token()
        request = Request(
            self.api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": token,
                "Content-Type": "application/json;charset=UTF-8",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
        payload = json.loads(raw_text)
        return _extract_product_records(payload.get("data"))

    def _fetch_product_list(self, main_sku: str) -> list[dict]:
        token = self._authorization_token()
        for query_value in get_product_list_query_values(main_sku):
            body = json.dumps(
                {"filter1value": query_value, "status": "8", "page": 1, "limit": 100, "isfile": 0},
                ensure_ascii=False,
            ).encode("utf-8")
            request = Request(
                self.product_list_api_url,
                data=body,
                method="POST",
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json;charset=UTF-8",
                },
            )
            with urlopen(request, timeout=self.timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw_text)
            records = _extract_product_records(payload.get("data"))
            if records:
                return records
        return []

    def _authorization_token(self) -> str:
        if self.login_username and self.login_password:
            if not self.login_token:
                self.login_token = self._login()
            return self.login_token
        return self.token

    def _login(self) -> str:
        body = json.dumps(
            {"username": self.login_username, "password": self.login_password},
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if self.token:
            headers["Authorization"] = self.token
        request = Request(self.login_api_url, data=body, method="POST", headers=headers)
        with urlopen(request, timeout=self.timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
        token = extract_login_access_token(json.loads(raw_text))
        if not token:
            raise RuntimeError("ERP login succeeded but no access token was returned")
        return token


def build_url_search_body(image_url: str, top_n: int = 10) -> dict:
    top_n = max(1, int(top_n or 1))
    body = {"picUrl": image_url, "imageUrl": image_url, "fileUrl": image_url}
    for key in ("topN", "topK", "limit", "pageSize", "size", "count", "top_num", "top", "k", "num"):
        body[key] = top_n
    return body


def build_url_search_request_url(url: str, top_n: int = 10) -> str:
    count = max(1, int(top_n or 1))
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key in ("topN", "topK", "limit", "pageSize", "size", "count", "top_num", "top", "k", "num"):
        query.setdefault(key, str(count))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def extract_login_access_token(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("accessToken", "token", "authorization", "Authorization"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        return extract_login_access_token(data)
    return ""


def normalize_sku_lookup_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").strip().upper())


def get_product_list_query_values(main_sku: str) -> list[str]:
    values = []
    for value in (str(main_sku or "").strip(), normalize_sku_lookup_key(main_sku)):
        if value and value not in values:
            values.append(value)
    return values


def input_csv_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    filename_by_source = {
        "seerfar": "seerfar_products.csv",
        "ixspy": "aliexpress_products.csv",
        "aliexpress": "aliexpress_products.csv",
    }
    directory_by_source = {
        "seerfar": "seerfar",
        "ixspy": "aliexpress",
        "aliexpress": "aliexpress",
    }
    if source not in filename_by_source:
        raise RuntimeError(f"Unsupported image-search source: {source}")
    return (
        Path(base_dir)
        / "input"
        / directory_by_source[source]
        / product_type
        / filename_by_source[source]
    )


def output_csv_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "erp_image_search_results.csv"


def boss_decision_csv_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "boss_decision_report.csv"


def boss_decision_markdown_path(base_dir: str | Path, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "boss_decision_report.md"


def load_external_rows(path: str | Path, *, source: str, product_type: str) -> list[dict]:
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            image_url = (row.get("image_url") or "").strip()
            if not image_url:
                continue
            external = {
                "source": source,
                "product_type": product_type,
                "external_sku": (row.get("sku") or "").strip(),
                "external_product_name": (row.get("product_name") or "").strip(),
                "external_product_url": (row.get("product_url") or "").strip(),
                "external_image_url": image_url,
            }
            for key, value in row.items():
                external[f"external_{key}"] = (value or "").strip()
            rows.append(external)
    return rows


def normalize_search_response(payload: dict) -> SearchResult:
    data = payload.get("data")
    products = _extract_product_records(data)
    matches = []
    for product in products:
        if not isinstance(product, dict):
            continue
        matches.append(
            {
                "matched_erp_sku": _first(product, ["sku", "picName", "picname", "imageName", "mainSKu", "mainsku", "mainSku", "main_sku", "mainSKU"]),
                "matched_main_sku": _first(product, ["mainSKu", "mainsku", "mainSku", "main_sku", "mainSKU", "mainSkuCode", "parentSku", "spuCode"]),
                "erp_product_status": _first(product, ["productStatus", "statusName", "statusText", "status"]),
                "erp_image_url": _first(product, ["url", "picUrl", "imageUrl", "imgUrl", "fileUrl"]),
                "similarity": _number(_first(product, ["similarity", "score", "similarScore", "matchScore"])),
                "match_source": _first(product, ["matchSource", "source"]) or "erp_image_search",
            }
        )
    matches.sort(key=lambda match: _sort_number(match.get("similarity")), reverse=True)
    for index, match in enumerate(matches, start=1):
        match["match_rank"] = index
    # ERP 鉴权失败用 {"status":404} 而非 {"code":...}；缺 code 时回退用数字 status 当 code，
    # 否则 404 会被误判成 empty，导致 token 过期时自动刷新无法触发。
    code = payload.get("code")
    if code is None and isinstance(payload.get("status"), int):
        code = payload.get("status")
    status = "success" if code == 200 and matches else "empty"
    if code not in (None, 200):
        status = "error"
    return SearchResult(
        status=status,
        code=code,
        message=str(payload.get("msg") or payload.get("message") or ""),
        trace_id=str(payload.get("traceId") or ""),
        matches=matches,
        raw=payload,
    )


def _extract_product_records(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []

    collection_keys = (
        "records", "list", "rows", "items", "products", "productList",
        "skuList", "subSkus", "subSkuList", "sonSkuList", "children",
        "result", "results", "data",
    )
    for key in collection_keys:
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            records = _extract_product_records(nested)
            if records:
                return records

    product_keys = {
        "sku", "picName", "picname", "imageName", "mainSKu", "mainsku",
        "mainSku", "main_sku", "mainSKU", "mainSkuCode", "parentSku",
        "spuCode", "url", "picUrl", "imageUrl", "imgUrl", "fileUrl",
    }
    if any(key in value for key in product_keys):
        return [value]
    return []


def enrich_matches_with_sub_skus(matches: list[dict], fetcher) -> list[dict]:
    cache: dict[str, list[dict]] = {}
    enriched = []
    for match in matches:
        row = dict(match)
        main_sku = (row.get("matched_main_sku") or "").strip()
        sub_skus = []
        if main_sku:
            if main_sku not in cache:
                try:
                    cache[main_sku] = fetcher(main_sku) or []
                except Exception as error:
                    cache[main_sku] = []
                    row["erp_subsku_error"] = f"{type(error).__name__}: {error}"
            sub_skus = cache[main_sku]
        _merge_sub_sku_summary(row, sub_skus)
        enriched.append(row)
    return enriched


def _merge_sub_sku_summary(row: dict, sub_skus: list[dict]) -> None:
    row["erp_subsku_count"] = len(sub_skus)
    row["erp_total_inventory"] = _sum_numbers(sub_skus, ["inventory", "totalinventory", "stock", "quantity"])
    row["erp_sales_num"] = _sum_numbers(sub_skus, ["salesnum", "salesNum", "sales", "saleNum", "singledaysales", "salesDay"])
    selected = _select_sub_sku(row.get("matched_erp_sku", ""), sub_skus)
    if not row.get("erp_product_status"):
        detail_status = _first(selected, ["productStatus", "status", "statusName", "statusText"])
        if detail_status:
            row["erp_product_status"] = detail_status
    row["erp_cost_price"] = _number(_first(selected, ["costprice", "costPrice", "cost", "purchasePrice"]))
    row["erp_sell_price"] = _number(_first(selected, ["skusell", "skuSell", "sellPrice", "salePrice", "price"]))
    row["erp_subsku_json"] = json.dumps(sub_skus, ensure_ascii=False, sort_keys=True) if sub_skus else ""


def _select_sub_sku(matched_sku: str, sub_skus: list[dict]) -> dict:
    normalized = normalize_sku_lookup_key(matched_sku)
    for sub_sku in sub_skus:
        sku = normalize_sku_lookup_key(_first(sub_sku, ["sku", "subsku", "subSku", "skuCode"]))
        if normalized and sku == normalized:
            return sub_sku
    return sub_skus[0] if sub_skus else {}


def merge_product_list_details(records: list[dict], product_list: list[dict]) -> list[dict]:
    extras = {}
    for product in product_list or []:
        sku = _first(product, ["sku", "subsku", "subSku", "skuCode", "productSku", "localSku"])
        if not sku:
            continue
        extras[str(sku).strip()] = product
        normalized = normalize_sku_lookup_key(sku)
        if normalized:
            extras[normalized] = product

    merged = []
    for record in records or []:
        row = dict(record)
        sku = _first(row, ["sku", "subsku", "subSku", "skuCode", "productSku", "localSku"])
        extra = extras.get(str(sku).strip()) or extras.get(normalize_sku_lookup_key(sku))
        if extra:
            _copy_first_present(row, extra, ["inventory", "totalinventory", "stock", "quantity"])
            _copy_first_present(row, extra, ["costprice", "costPrice", "cost", "purchasePrice"])
            _copy_first_present(row, extra, ["singledaysales", "salesDay", "salesnum", "salesNum", "sales", "saleNum"])
            _copy_first_present(row, extra, ["pic3", "pic1", "pic2", "url", "picUrl", "imageUrl", "imgUrl", "fileUrl"])
            _copy_first_present(row, extra, ["productStatus", "status", "statusName", "statusText"])
        merged.append(row)
    return merged


def _copy_first_present(target: dict, source: dict, keys: list[str]) -> None:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            target[key] = value
            return


def _sum_numbers(rows: list[dict], keys: list[str]):
    total = 0.0
    seen = False
    for row in rows:
        value = _number(_first(row, keys))
        if value == "":
            continue
        total += float(value)
        seen = True
    if not seen:
        return ""
    return int(total) if total.is_integer() else total


def _default_token_refresher(base_dir: str):
    from sourcing.erp_token import refresh_erp_token  # 懒导入避免循环
    return refresh_erp_token(base_dir)


def _is_auth_failure(result) -> bool:
    """判断图搜结果是否像 token 过期/鉴权失败(而非正常的'没匹配到')。"""
    if getattr(result, "status", None) != "error":
        return False
    message = (getattr(result, "message", "") or "").lower()
    code = getattr(result, "code", None)
    return code in (401, 403, 404) or any(
        kw in message for kw in ("not found", "token", "unauth", "登录", "鉴权"))


def refresh_image_search_client_token(client: ErpImageSearchClient) -> str:
    """Log in once and apply the fresh credential to both ERP image-search modes."""
    token = ErpSubSkuClient(timeout=client.timeout)._login()
    client.token = token
    if client.url_api_token:
        client.url_api_token = token
    return token


def refresh_image_search_client_token(client: ErpImageSearchClient) -> str:
    """Log in once and apply the fresh credential to both ERP image-search modes."""
    token = ErpSubSkuClient(timeout=client.timeout)._login()
    client.token = token
    if client.url_api_token:
        client.url_api_token = token
    return token


def run_image_search(
    *,
    source: str,
    product_type: str,
    base_dir: str | Path = ".",
    limit: int | None = None,
    delay_seconds: float = 0.5,
    search_func=None,
    sub_sku_fetcher=None,
    enrich_sub_skus: bool | None = None,
    sleep_func=time.sleep,
    max_retries: int = 3,
    token_refresher=None,
) -> dict:
    input_path = input_csv_path(base_dir, source, product_type)
    rows = load_external_rows(input_path, source=source, product_type=product_type)
    if limit is not None:
        rows = rows[:limit]

    client = None
    sub_sku_client = None
    if search_func is None:
        client = ErpImageSearchClient()
        search_func = client.search
    if enrich_sub_skus is None:
        enrich_sub_skus = os.environ.get("ERP_IMAGE_SEARCH_ENRICH_SUB_SKUS", "").lower() in {"1", "true", "yes"}
    if enrich_sub_skus and sub_sku_fetcher is None:
        sub_sku_client = ErpSubSkuClient(token=client.token if client is not None else None)
        sub_sku_fetcher = sub_sku_client.fetch

    refreshed = False
    output_rows = []
    for index, external in enumerate(rows):
        result = _search_with_retries(
            search_func, external["external_image_url"],
            max_retries=max_retries, sleep_func=sleep_func,
        )
        # token 过期自动刷新一次后重试(只刷新一次, 避免反复登录)
        can_refresh = client is not None or token_refresher is not None
        if can_refresh and not refreshed and _is_auth_failure(result):
            refreshed = True
            refresher = token_refresher or _default_token_refresher
            new_token = refresher(str(base_dir))
            if client is not None and new_token:
                client.token = new_token
            if sub_sku_client is not None and new_token:
                sub_sku_client.token = new_token
            result = _search_with_retries(
                search_func, external["external_image_url"],
                max_retries=max_retries, sleep_func=sleep_func,
            )
        if enrich_sub_skus and result.matches and sub_sku_fetcher is not None:
            result = SearchResult(
                status=result.status,
                code=result.code,
                message=result.message,
                trace_id=result.trace_id,
                matches=enrich_matches_with_sub_skus(result.matches, sub_sku_fetcher),
                raw=result.raw,
            )
        output_rows.extend(_result_rows(external, result))
        if delay_seconds > 0 and index < len(rows) - 1:
            sleep_func(delay_seconds)

    output_path = write_csv(str(output_csv_path(base_dir, source, product_type)), output_rows, _fields_with_extras(RESULT_FIELDS, output_rows))
    return {
        "source": source,
        "product_type": product_type,
        "input": str(input_path),
        "output": output_path,
        "searched": len(rows),
        "written": len(output_rows),
    }


def _search_with_retries(search_func, image_url: str, *, max_retries: int, sleep_func=time.sleep) -> SearchResult:
    last_error = None
    for attempt in range(1, max(1, max_retries) + 1):
        try:
            result = search_func(image_url)
            if not _is_retryable_search_result(result) or attempt >= max(1, max_retries):
                return result
            last_error = RuntimeError(f"ERP temporary error: {result.code} {result.message}")
        except Exception as error:
            last_error = error
        if attempt < max_retries:
            sleep_func(min(2 * attempt, 10))
    message = f"{type(last_error).__name__}: {last_error}" if last_error else "unknown error"
    return SearchResult(
        status="error",
        code=None,
        message=message,
        trace_id="",
        matches=[],
        raw={"error": message},
    )


def _is_retryable_search_result(result: SearchResult) -> bool:
    return result.status == "error" and result.code in {408, 425, 429, 500, 502, 503, 504}


def generate_boss_decision_report(
    *,
    source: str,
    product_type: str,
    base_dir: str | Path = ".",
) -> dict:
    input_path = output_csv_path(base_dir, source, product_type)
    rows = _read_csv_dicts(input_path)
    decisions = build_boss_decision_rows(rows)
    fields = _fields_with_extras(BOSS_DECISION_FIELDS, decisions)
    csv_path = write_csv(
        str(boss_decision_csv_path(base_dir, source, product_type)),
        _localized_rows(decisions, BOSS_DECISION_FIELD_LABELS),
        [_field_label(field, BOSS_DECISION_FIELD_LABELS) for field in fields],
    )
    markdown_path = boss_decision_markdown_path(base_dir, source, product_type)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_boss_decision_markdown(decisions, source, product_type), encoding="utf-8")
    return {
        "source": source,
        "product_type": product_type,
        "input": str(input_path),
        "csv": csv_path,
        "markdown": str(markdown_path),
        "products": len(decisions),
    }


def build_boss_decision_rows(rows: list[dict]) -> list[dict]:
    groups = {}
    order = []
    for row in rows:
        key = (
            row.get("source") or "",
            row.get("product_type") or "",
            row.get("external_sku") or "",
            row.get("external_product_url") or "",
            row.get("external_image_url") or "",
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    decisions = []
    for key in order:
        items = groups[key]
        first = items[0]
        normal = _count_priority(items, "可用正常商品")
        stopped = _count_priority(items, "疑似同款但停产")
        limited = _count_priority(items, "疑似同款但采购受限")
        risk = _count_priority(items, "疑似同款但风险商品")
        final_decision, boss_action = _boss_decision(normal, stopped, limited, risk, items)
        decisions.append(
            {
                "source": first.get("source", ""),
                "product_type": first.get("product_type", ""),
                "external_sku": first.get("external_sku", ""),
                "external_product_name": first.get("external_product_name", ""),
                "external_product_url": first.get("external_product_url", ""),
                "external_image_url": first.get("external_image_url", ""),
                "external_source_rank": first.get("external_source_rank", ""),
                "external_brand": first.get("external_brand", ""),
                "external_category": first.get("external_category", ""),
                "external_price": first.get("external_price", ""),
                "external_sales": first.get("external_sales", ""),
                "external_sales_1y": first.get("external_sales_1y", ""),
                "external_sales_7d": first.get("external_sales_7d", ""),
                "external_review_count": first.get("external_review_count", ""),
                "external_comments_1y": first.get("external_comments_1y", ""),
                "external_rating": first.get("external_rating", ""),
                "external_weekly_growth": first.get("external_weekly_growth", ""),
                "external_first_found_at": first.get("external_first_found_at", ""),
                "external_avg_daily_sales_1y": first.get("external_avg_daily_sales_1y", ""),
                "external_fulfillment_type": first.get("external_fulfillment_type", ""),
                "external_choice": first.get("external_choice", ""),
                "external_choice_type": first.get("external_choice_type", ""),
                "external_seller_id": first.get("external_seller_id", ""),
                "external_seller_name": first.get("external_seller_name", ""),
                "external_seller_positive_rate": first.get("external_seller_positive_rate", ""),
                "final_decision": final_decision,
                "boss_action": boss_action,
                "candidate_count": len([item for item in items if item.get("matched_erp_sku")]),
                "normal_candidate_count": normal,
                "stopped_candidate_count": stopped,
                "limited_candidate_count": limited,
                "risk_candidate_count": risk,
                "top_erp_skus": _join_unique(items, "matched_erp_sku"),
                "top_main_skus": _join_unique(items, "matched_main_sku"),
                "max_embedding_similarity": _max_embedding(items),
            }
        )
    return decisions


def render_boss_decision_markdown(decisions: list[dict], source: str, product_type: str) -> str:
    lines = [
        "# ERP 以图搜索老板决策报告",
        "",
        f"数据来源：{source}",
        f"品类：{product_type}",
        "",
        "## 决策摘要",
        "",
        "| 平台SKU | 商品名称 | 价格 | 近一年销量 | 近一年评论 | 7天销量 | 周增长 | 日均销量 | 首次发现 | 托管类型 | 结论 | 建议动作 | ERP候选 | 正常候选 | 停产候选 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in decisions:
        lines.append(
            "| {external_sku} | {external_product_name} | {external_price} | {external_sales} | "
            "{external_review_count} | {external_sales_7d} | {external_weekly_growth} | "
            "{external_avg_daily_sales_1y} | {external_first_found_at} | {external_fulfillment_type} | "
            "{final_decision} | {boss_action} | "
            "{candidate_count} | {normal_candidate_count} | {stopped_candidate_count} |".format(
                **{key: _md_cell(value) for key, value in row.items()}
            )
        )

    lines.extend(["", "## 明细", ""])
    for row in decisions:
        lines.extend(
            [
                f"### {row.get('external_sku') or '无平台SKU'}",
                "",
                f"- 商品名称：{row.get('external_product_name') or '-'}",
                f"- 外部平台价格：{row.get('external_price') or '-'}",
                f"- 近一年销量：{row.get('external_sales') or '-'}",
                f"- 近一年评论数：{row.get('external_review_count') or '-'}",
                f"- 近 7 天销量：{row.get('external_sales_7d') or '-'}",
                f"- 周增长数：{row.get('external_weekly_growth') or '-'}",
                f"- 近一年日均销量：{row.get('external_avg_daily_sales_1y') or '-'}",
                f"- 首次发现时间：{row.get('external_first_found_at') or '-'}",
                f"- 托管类型：{row.get('external_fulfillment_type') or '-'}",
                f"- 评分：{row.get('external_rating') or '-'}",
                f"- 店铺：{row.get('external_seller_name') or '-'}",
                f"- 最终结论：{row.get('final_decision')}",
                f"- 建议动作：{row.get('boss_action')}",
                f"- ERP 候选 SKU：{row.get('top_erp_skus') or '-'}",
                f"- ERP 主 SKU：{row.get('top_main_skus') or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def _result_rows(external: dict, result: SearchResult) -> list[dict]:
    searched_at = datetime.now(timezone.utc).isoformat()
    raw_json = json.dumps(result.raw, ensure_ascii=False, sort_keys=True)
    matches = result.matches or [{}]
    rows = []
    for match in matches:
        status_code = str(match.get("erp_product_status", "") or "")
        status_text = format_product_status(status_code)
        rows.append(
            {
                **external,
                "match_status": result.status,
                "match_rank": match.get("match_rank", ""),
                "match_source": match.get("match_source", ""),
                "matched_erp_sku": match.get("matched_erp_sku", ""),
                "matched_main_sku": match.get("matched_main_sku", ""),
                "erp_product_status": status_code,
                "erp_product_status_text": status_text,
                "candidate_priority": candidate_priority(result.status, status_code),
                "erp_image_url": match.get("erp_image_url", ""),
                "similarity": match.get("similarity", ""),
                "erp_subsku_count": match.get("erp_subsku_count", ""),
                "erp_total_inventory": match.get("erp_total_inventory", ""),
                "erp_cost_price": match.get("erp_cost_price", ""),
                "erp_sell_price": match.get("erp_sell_price", ""),
                "erp_sales_num": match.get("erp_sales_num", ""),
                "erp_subsku_json": match.get("erp_subsku_json", ""),
                "message": result.message,
                "code": result.code if result.code is not None else "",
                "trace_id": result.trace_id,
                "searched_at": searched_at,
                "raw_json": raw_json,
            }
        )
    return rows


def format_product_status(status: str) -> str:
    normalized = str(status or "").strip()
    if not normalized:
        return ""
    return PRODUCT_STATUS_MAP.get(normalized, normalized)


def candidate_priority(match_status: str, product_status: str) -> str:
    if match_status != "success":
        return "需人工确认"
    normalized = str(product_status or "").strip()
    if normalized == "8":
        return "可用正常商品"
    if normalized == "1":
        return "疑似同款但停产"
    if normalized in {"2", "6", "10"}:
        return "疑似同款但采购受限"
    if normalized in {"4", "5", "11", "12", "13", "14"}:
        return "疑似同款但风险商品"
    return "需人工确认"


def _read_csv_dicts(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _count_priority(rows: list[dict], priority: str) -> int:
    return sum(1 for row in rows if (row.get("candidate_priority") or "").strip() == priority)


def _max_embedding(rows: list[dict]):
    vals = []
    for row in rows:
        v = row.get("embedding_similarity")
        if v in (None, "", "None"):
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(vals) if vals else ""


def _boss_decision(
    normal_count: int,
    stopped_count: int,
    limited_count: int,
    risk_count: int,
    rows: list[dict],
) -> tuple[str, str]:
    if normal_count:
        return "疑似已有正常同款", "先人工确认正常候选；确认同款后不要作为新品开发"
    if risk_count:
        return "疑似风险同款", "先走合规审核；未确认前不要推进开发"
    if stopped_count:
        return "有历史停产同款", "查停产原因和供应链；可作为恢复或重新开发机会"
    if limited_count:
        return "有采购受限同款", "先确认采购能否恢复；不能恢复再按新品机会评估"
    if any(row.get("matched_erp_sku") for row in rows):
        return "需人工确认", "候选信息不足；人工确认是否同款"
    return "疑似新品机会", "ERP 未找到明确候选；进入新品机会池继续评估销量和利润"


def _join_unique(rows: list[dict], field: str, limit: int = 5) -> str:
    values = []
    seen = set()
    for row in rows:
        value = (row.get(field) or "").strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
        if len(values) >= limit:
            break
    return ", ".join(values)


def _md_cell(value) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "/").replace("\r", " ").replace("\n", " ")


def _fields_with_extras(base_fields: list[str], rows: list[dict]) -> list[str]:
    fields = list(base_fields)
    seen = set(fields)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def _field_label(field: str, labels: dict[str, str]) -> str:
    return labels.get(field, field)


def _localized_rows(rows: list[dict], labels: dict[str, str]) -> list[dict]:
    return [
        {_field_label(key, labels): value for key, value in row.items()}
        for row in rows
    ]


def _first(product: dict, keys: list[str]) -> str:
    for key in keys:
        value = product.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _number(value: str):
    if value == "":
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return ""


def _sort_number(value) -> float:
    parsed = _number(value)
    return float(parsed) if parsed != "" else -1.0


def _build_multipart_body(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----ProductSourcing{uuid.uuid4().hex}"
    chunks = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


# 老板版报告的外部业务字段：报表列名 -> 输入CSV里可能的列名(按序取第一个非空)
_EXTERNAL_BIZ_FIELDS = [
    ("品牌", ["brand"]),
    ("类目", ["category"]),
    ("单价", ["price"]),
    ("近一年销量", ["sales_1y", "sales"]),
    ("近一年评论数", ["comments_1y", "review_count"]),
    ("近7天销量", ["sales_7d"]),
    ("周增长数", ["weekly_growth"]),
    ("首次发现时间", ["first_found_at"]),
    ("近一年日均销量", ["avg_daily_sales_1y"]),
    ("托管类型", ["fulfillment_type"]),
    ("评分", ["rating", "review_rating"]),
    ("卖家", ["seller_name"]),
    ("卖家好评率", ["seller_positive_rate"]),
]

BEST_MATCH_FIELDS = [
    "竞品SKU", "竞品名称", "品牌", "类目", "单价", "近一年销量", "近一年评论数",
    "近7天销量", "周增长数", "首次发现时间", "近一年日均销量", "托管类型",
    "评分", "卖家", "卖家好评率", "竞品图", "竞品链接",
    "最像ERP_SKU", "ERP主SKU", "ERP商品状态", "ERP候选图", "嵌入相似度", "匹配判定",
]


def _biz(row: dict, names: list[str]):
    for name in names:
        value = row.get(name)
        if value not in (None, "", "None"):
            return value
    return ""


def _value(row: dict, name: str):
    value = row.get(name)
    return "" if value in (None, "None") else value


def _format_decimal(value, places: int = 2) -> str:
    if value in (None, "", "None"):
        return ""
    try:
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return str(value)


def _erp_status_text(match: dict) -> str:
    status_text = _value(match, "erp_product_status_text")
    if status_text:
        return str(status_text)
    status_code = _value(match, "erp_product_status")
    if not status_code:
        status_code = _status_from_subsku_json(match)
    return format_product_status(str(status_code)) if status_code else ""


def _status_from_subsku_json(match: dict) -> str:
    raw = _value(match, "erp_subsku_json")
    if not raw:
        return ""
    try:
        sub_skus = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(sub_skus, list):
        return ""
    selected = _select_sub_sku(str(_value(match, "matched_erp_sku")), sub_skus)
    return _first(selected, ["productStatus", "status", "statusName", "statusText"])


def _embedding_value(row: dict) -> float:
    try:
        return float(row.get("embedding_similarity"))
    except (TypeError, ValueError):
        return -1.0


def best_match_verdict(sim: float) -> str:
    if sim < 0:
        return "无图(竞品图失败)"
    if sim >= 0.85:
        return "高置信匹配"
    if sim >= 0.70:
        return "可能匹配"
    if sim >= 0.50:
        return "弱匹配(需人工)"
    return "无匹配(疑似不同款)"


def build_best_match_rows(rows: list[dict], external_index: dict | None = None) -> list[dict]:
    """每个竞品取嵌入相似度最高的候选(B口径: 无匹配也保留最像候选), 输出一商品一行。
    external_index: {external_sku: 输入CSV行} —— 给齐了就把单价/销量等业务字段合进来(老板版)。"""
    external_index = external_index or {}
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        key = row.get("external_sku") or ""
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    out = []
    for key in order:
        items = groups[key]
        candidates = [it for it in items if it.get("erp_image_url")] or items
        best = max(candidates, key=_embedding_value)
        sim = _embedding_value(best)
        ext = external_index.get(key, {})
        out.append({
            "竞品SKU": key,
            "竞品名称": (best.get("external_product_name") or "")[:60],
            **{col: _biz(ext, names) for col, names in _EXTERNAL_BIZ_FIELDS},
            "竞品图": best.get("external_image_url", ""),
            "竞品链接": best.get("external_product_url", ""),
            "最像ERP_SKU": best.get("matched_erp_sku", ""),
            "ERP主SKU": best.get("matched_main_sku", ""),
            "ERP商品状态": best.get("erp_product_status_text", ""),
            "ERP候选图": best.get("erp_image_url", ""),
            "嵌入相似度": round(sim, 4) if sim >= 0 else "",
            "匹配判定": best_match_verdict(sim),
        })
    return out


def best_match_csv_path(base_dir, source: str, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / source / product_type / "best_match_report.csv"


SEERFAR_ENRICHED_REPORT_FIELDS = [
    "排名",
    "SeerFar SKU",
    "SeerFar 标题",
    "SeerFar 主图",
    "SeerFar 商品链接",
    "品牌",
    "类目",
    "销售方式",
    "SeerFar 售价",
    "币种",
    "SeerFar 销量",
    "SeerFar 销售额",
    "SeerFar 毛利率",
    "SeerFar 评论数",
    "SeerFar 评分",
    "SeerFar 重量",
    "SeerFar 体积",
    "店铺",
    "卖家类型",
    "配送方式",
    "匹配判定",
    "嵌入相似度",
    "ERP以图搜索相似度",
    "ERP候选排名",
    "ERP子SKU",
    "ERP主SKU",
    "ERP商品状态",
    "ERP图片链接",
    "ERP库存",
    "ERP销量",
    "ERP子SKU数量",
    "建议动作",
]

SEERFAR_BOSS_REPORT_VERDICTS = {"高置信匹配", "可能匹配"}


def seerfar_enriched_report_path(base_dir, product_type: str) -> Path:
    return Path(base_dir) / "output" / "image_search" / "seerfar" / product_type / "seerfar_enriched_report.csv"


def build_seerfar_enriched_report_rows(source_rows: list[dict], match_rows: list[dict]) -> list[dict]:
    best_by_sku = _best_match_by_external_sku(match_rows)
    rows = []
    for source_row in source_rows:
        sku = (source_row.get("sku") or "").strip()
        match = best_by_sku.get(sku, {})
        embedding = _value(match, "embedding_similarity")
        erp_similarity = _value(match, "similarity")
        erp_status_text = _erp_status_text(match)
        verdict = best_match_verdict(_embedding_value(match)) if match else "未参与本次匹配"
        rows.append({
            "排名": _value(source_row, "source_rank"),
            "SeerFar SKU": sku,
            "SeerFar 标题": _value(source_row, "product_name"),
            "SeerFar 主图": _value(source_row, "image_url"),
            "SeerFar 商品链接": _value(source_row, "product_url"),
            "品牌": _value(source_row, "brand"),
            "类目": _value(source_row, "category"),
            "销售方式": _value(source_row, "sale_mode"),
            "SeerFar 售价": _value(source_row, "price"),
            "币种": _value(source_row, "currency"),
            "SeerFar 销量": _value(source_row, "sales"),
            "SeerFar 销售额": _value(source_row, "sales_revenue"),
            "SeerFar 毛利率": _value(source_row, "gross_margin"),
            "SeerFar 评论数": _value(source_row, "review_count"),
            "SeerFar 评分": _value(source_row, "review_rating"),
            "SeerFar 重量": _value(source_row, "weight"),
            "SeerFar 体积": _value(source_row, "volume"),
            "店铺": _value(source_row, "seller_name"),
            "卖家类型": _value(source_row, "seller_type"),
            "配送方式": _value(source_row, "delivery_method"),
            "匹配判定": verdict,
            "嵌入相似度": embedding,
            "ERP以图搜索相似度": erp_similarity,
            "ERP候选排名": _value(match, "match_rank"),
            "ERP子SKU": _value(match, "matched_erp_sku"),
            "ERP主SKU": _value(match, "matched_main_sku"),
            "ERP商品状态": erp_status_text,
            "ERP图片链接": _value(match, "erp_image_url"),
            "ERP库存": _value(match, "erp_total_inventory"),
            "ERP销量": _value(match, "erp_sales_num"),
            "ERP子SKU数量": _value(match, "erp_subsku_count"),
            "建议动作": _seerfar_action(verdict, erp_status_text),
        })
    return rows


def _seerfar_boss_report_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("匹配判定") in SEERFAR_BOSS_REPORT_VERDICTS]


def generate_seerfar_enriched_report(*, product_type: str, base_dir=".") -> dict:
    source_rows = _read_csv_dicts(input_csv_path(base_dir, "seerfar", product_type))
    match_rows = _read_csv_dicts(output_csv_path(base_dir, "seerfar", product_type))
    rows = build_seerfar_enriched_report_rows(source_rows, match_rows)
    report_rows = _seerfar_boss_report_rows(rows)
    csv_path = write_csv(
        str(seerfar_enriched_report_path(base_dir, product_type)),
        report_rows,
        SEERFAR_ENRICHED_REPORT_FIELDS,
    )
    verdicts: dict[str, int] = {}
    for row in report_rows:
        verdict = row.get("匹配判定", "")
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    return {
        "source": "seerfar",
        "product_type": product_type,
        "products": len(report_rows),
        "verdicts": verdicts,
        "csv": csv_path,
    }


def _best_match_by_external_sku(rows: list[dict]) -> dict[str, dict]:
    best = {}
    for row in rows:
        sku = (row.get("external_sku") or "").strip()
        if not sku:
            continue
        current = best.get(sku)
        if current is None or _embedding_value(row) > _embedding_value(current):
            best[sku] = row
    return best


def _seerfar_action(verdict: str, erp_status_text: str) -> str:
    if verdict == "未参与本次匹配":
        return "本次样本未覆盖；正式判断前需要先执行 ERP 以图搜索和 DINOv2 精筛"
    if verdict == "高置信匹配":
        if "正常" in erp_status_text:
            return "高置信同款，ERP 正常在售；通常不作为新品，优先评估跟卖/价格/库存策略"
        return "高置信同款，先确认 ERP 状态、库存和供应链；正常在售则不作为新品，停产/缺货可评估恢复或替代开发"
    if verdict == "可能匹配":
        return "可能同款，建议人工看图确认；确认同款后再看 ERP 库存、成本和销售表现"
    if verdict.startswith("弱匹配"):
        return "相似度偏低，仅作线索；人工确认后再决定是否进入开发池"
    if verdict.startswith("无图"):
        return "图片下载或识别失败，先补图或换图后重跑"
    return "未发现明确同款，可进入新品机会池继续评估销量、利润和供应链"


def _external_index(base_dir, source: str, product_type: str) -> dict:
    """从输入CSV按 sku 建索引，给老板版报告补业务字段。读不到就返回空。"""
    index = {}
    try:
        for row in _read_csv_dicts(input_csv_path(base_dir, source, product_type)):
            sku = (row.get("sku") or "").strip()
            if sku:
                index[sku] = row
    except (FileNotFoundError, OSError):
        pass
    return index


def generate_best_match_report(*, source: str, product_type: str, base_dir="." ) -> dict:
    rows = _read_csv_dicts(output_csv_path(base_dir, source, product_type))
    out = build_best_match_rows(rows, _external_index(base_dir, source, product_type))
    out.sort(key=lambda r: r["嵌入相似度"] if isinstance(r["嵌入相似度"], float) else -1.0,
             reverse=True)
    csv_path = write_csv(str(best_match_csv_path(base_dir, source, product_type)),
                         out, BEST_MATCH_FIELDS)
    verdicts: dict[str, int] = {}
    for r in out:
        verdicts[r["匹配判定"]] = verdicts.get(r["匹配判定"], 0) + 1
    return {"source": source, "product_type": product_type, "products": len(out),
            "verdicts": verdicts, "csv": csv_path}
