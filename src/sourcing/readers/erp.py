from sourcing.contracts import NormalizedProduct
from sourcing.readers.common import read_csv_rows, to_float, to_int

SOURCE = "erp"


def read_erp(path: str, product_type: str):
    rows = read_csv_rows(path)
    products, skus = [], []
    for row in rows:
        sku = (row.get("sku") or "").strip()
        products.append(NormalizedProduct(
            source=SOURCE, platform="erp", platform_product_id=None,
            canonical_url=None, source_record_id=sku or f"row-{len(products)}",
            product_type=product_type, title=row.get("product_name") or None,
            category=row.get("category") or None, image_url=row.get("image_url") or None,
            is_own=True,
        ))
        skus.append({
            "sku": sku,
            "cost_price": to_float(row.get("cost_price")),
            "weighted_purchase": to_float(row.get("weighted_purchase")),
            "weighted_freight": to_float(row.get("weighted_freight")),
            "weighted_sorting": to_float(row.get("weighted_sorting")),
            "stock": to_int(row.get("stock")),
            "once_gross_margin": to_float(row.get("once_gross_margin")),
            "main_platform": row.get("main_platform") or None,
        })
    return products, skus
