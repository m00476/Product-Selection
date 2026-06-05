import json

from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot
from sourcing.readers.common import read_csv_rows, to_float, to_int, now_utc
from sourcing.urls import normalize_product_url

SOURCE = "seerfar"


def _raw_json(row: dict) -> dict:
    value = row.get("raw_json")
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _metric(row: dict, raw: dict, csv_key: str, raw_key: str):
    value = to_float(row.get(csv_key))
    if value is not None:
        return value
    return to_float(raw.get(raw_key))


def _extra_metrics(row: dict) -> dict:
    raw = _raw_json(row)
    metrics = {
        "gross_margin": _metric(row, raw, "gross_margin", "grossMargin"),
        "views": _metric(row, raw, "views", "views"),
        "order_conversion_rate": _metric(row, raw, "order_conversion_rate", "orderConversionRate"),
        "return_cancellation_rate": _metric(row, raw, "return_cancellation_rate", "returnCancellationRate"),
        "missed_revenue": _metric(row, raw, "missed_revenue", "missedRevenue"),
        "category_rank": _metric(row, raw, "category_rank", "categoryRank"),
    }
    return {key: value for key, value in metrics.items() if value is not None}


def read_seerfar(path: str, product_type: str):
    rows = read_csv_rows(path)
    products, prices, sales = [], [], []
    collected = now_utc()
    for row in rows:
        platform, pid, canonical = normalize_product_url(row.get("product_url"))
        record_id = (row.get("sku") or "").strip() or (canonical or f"row-{len(products)}")
        products.append(NormalizedProduct(
            source=SOURCE, platform=platform, platform_product_id=pid,
            canonical_url=canonical, source_record_id=record_id, product_type=product_type,
            title=row.get("product_name") or None, brand=row.get("brand") or None,
            category=row.get("category") or None, image_url=row.get("image_url") or None,
            seller_id=row.get("seller_id") or None, seller_name=row.get("seller_name") or None,
            extra_metrics=_extra_metrics(row),
        ))
        prices.append(PriceSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            price=to_float(row.get("price")), currency=None,
            observed_at=collected, collected_at=collected, metric_source="seerfar",
        ))
        sales.append(SalesSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            sales=to_float(row.get("sales")), review_count=to_int(row.get("review_count")),
            review_rating=to_float(row.get("review_rating")),
            observed_at=collected, collected_at=collected, metric_source="seerfar",
        ))
    return products, prices, sales
