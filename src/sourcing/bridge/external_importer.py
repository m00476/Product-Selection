import sqlite3
from datetime import datetime, timezone

import psycopg

from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot
from sourcing.repository import (
    upsert_product, insert_price_snapshot, insert_sales_snapshot, link_source_record,
)
from sourcing.urls import normalize_product_url

SOURCE = "518"

_COLUMNS = ["platform", "external_product_id", "title", "category", "price",
            "main_image_url", "product_url", "sales"]


def _to_float(value):
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_external_products(app_db_path: str) -> list[dict]:
    """读 518 app.db 的 external_products（518 已抓的竞品目录）。"""
    conn = sqlite3.connect(app_db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM external_products")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def import_external_products(conn: psycopg.Connection, app_db_path: str) -> dict:
    """把 518 的 external_products 导入本系统 products + 快照 + 关联。

    用本系统的 URL 规范化从 product_url 推导真实市场(ozon/aliexpress)与 platform_product_id，
    保证与 match_results 的 external_product_id 对齐，桥接才能命中。
    """
    rows = read_external_products(app_db_path)
    collected = datetime.now(timezone.utc)
    imported = 0
    skipped = 0
    for row in rows:
        platform, pid, canonical = normalize_product_url(row.get("product_url"))
        if pid is None:
            skipped += 1
            continue
        product = NormalizedProduct(
            source=SOURCE, platform=platform, platform_product_id=pid,
            canonical_url=canonical,
            source_record_id=str(row.get("external_product_id") or pid),
            product_type="", title=row.get("title") or None,
            category=row.get("category") or None,
            image_url=row.get("main_image_url") or None,
        )
        product_id = upsert_product(conn, product)
        price = _to_float(row.get("price"))
        if price is not None:
            insert_price_snapshot(conn, product_id, PriceSnapshot(
                source=SOURCE, platform=platform, platform_product_id=pid,
                price=price, currency=None, observed_at=collected,
                collected_at=collected, metric_source="518"))
        sales = _to_float(row.get("sales"))
        if sales is not None:
            insert_sales_snapshot(conn, product_id, SalesSnapshot(
                source=SOURCE, platform=platform, platform_product_id=pid,
                sales=sales, review_count=None, review_rating=None,
                observed_at=collected, collected_at=collected, metric_source="518"))
        link_source_record(conn, product, product_id=product_id, raw_id=None)
        imported += 1
    return {"imported": imported, "skipped_no_id": skipped}
