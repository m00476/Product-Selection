from sourcing.contracts import NormalizedProduct, PriceSnapshot
from sourcing.readers.common import read_csv_rows, to_float, now_utc
from sourcing.urls import normalize_product_url

SOURCE = "ixspy"


def read_ixspy(path: str, product_type: str):
    rows = read_csv_rows(path)
    products, prices = [], []
    collected = now_utc()
    for row in rows:
        platform, pid, canonical = normalize_product_url(row.get("product_url"))
        record_id = (row.get("sku") or "").strip() or (canonical or f"row-{len(products)}")
        products.append(NormalizedProduct(
            source=SOURCE, platform=platform, platform_product_id=pid,
            canonical_url=canonical, source_record_id=record_id, product_type=product_type,
            title=row.get("product_name") or None, brand=row.get("brand") or None,
            category=row.get("category") or None, image_url=row.get("image_url") or None,
        ))
        prices.append(PriceSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            price=to_float(row.get("price")), currency=None,
            observed_at=collected, collected_at=collected, metric_source="ixspy",
        ))
    return products, prices
