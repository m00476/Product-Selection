from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot
from sourcing.readers.common import read_csv_rows, to_float, to_int, now_utc
from sourcing.urls import normalize_product_url

SOURCE = "ixspy"


def read_ixspy(path: str, product_type: str):
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
            extra_metrics={
                "sales_1y": row.get("sales_1y") or row.get("sales"),
                "comments_1y": row.get("comments_1y") or row.get("review_count"),
                "sales_7d": row.get("sales_7d"),
                "weekly_growth": row.get("weekly_growth"),
                "first_found_at": row.get("first_found_at"),
                "avg_daily_sales_1y": row.get("avg_daily_sales_1y"),
                "fulfillment_type": row.get("fulfillment_type"),
                "choice": row.get("choice"),
                "choice_type": row.get("choice_type"),
            },
        ))
        prices.append(PriceSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            price=to_float(row.get("price")), currency=None,
            observed_at=collected, collected_at=collected, metric_source="ixspy",
        ))
        sales.append(SalesSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            sales=to_float(row.get("sales_1y") or row.get("sales")),
            review_count=to_int(row.get("comments_1y") or row.get("review_count")),
            review_rating=to_float(row.get("rating")),
            observed_at=collected, collected_at=collected, metric_source="ixspy",
        ))
    return products, prices, sales
