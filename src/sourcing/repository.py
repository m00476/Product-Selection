import hashlib
import json

import psycopg

from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def insert_raw_record(conn: psycopg.Connection, *, source: str, platform: str,
                      product_type: str, source_file: str, source_record_id: str,
                      raw_payload: dict) -> int:
    """Append-only：内容变化才新增；与最新一条相同则返回其 id。"""
    payload_hash = _hash_payload(raw_payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, payload_hash FROM raw_source_records
            WHERE source=%s AND platform=%s AND source_record_id=%s
            ORDER BY collected_at DESC LIMIT 1
            """,
            (source, platform, source_record_id),
        )
        latest = cur.fetchone()
        if latest is not None and latest[1] == payload_hash:
            return latest[0]
        cur.execute(
            """
            INSERT INTO raw_source_records
                (source, platform, product_type, source_file, source_record_id,
                 raw_payload, payload_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (source, platform, product_type, source_file, source_record_id,
             json.dumps(raw_payload, ensure_ascii=False), payload_hash),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id


def upsert_product(conn: psycopg.Connection, p: NormalizedProduct) -> int:
    with conn.cursor() as cur:
        if not p.is_own and p.platform_product_id is not None:
            cur.execute(
                """
                SELECT product_id FROM products
                WHERE is_own = false AND platform = %s AND platform_product_id = %s
                """,
                (p.platform, p.platform_product_id),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE products SET title=COALESCE(%s, title),
                        category=COALESCE(%s, category), image_url=COALESCE(%s, image_url),
                        brand=COALESCE(%s, brand), seller_id=COALESCE(%s, seller_id),
                        seller_name=COALESCE(%s, seller_name)
                    WHERE product_id=%s
                    """,
                    (p.title, p.category, p.image_url, p.brand, p.seller_id,
                     p.seller_name, existing[0]),
                )
                conn.commit()
                return existing[0]
        cur.execute(
            """
            INSERT INTO products
                (platform, platform_product_id, title, category, image_url,
                 brand, seller_id, seller_name, is_own)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING product_id
            """,
            (p.platform, p.platform_product_id, p.title, p.category, p.image_url,
             p.brand, p.seller_id, p.seller_name, p.is_own),
        )
        product_id = cur.fetchone()[0]
    conn.commit()
    return product_id


def insert_price_snapshot(conn: psycopg.Connection, product_id: int, snap: PriceSnapshot,
                          raw_id: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO price_snapshots
                (product_id, source, platform, platform_product_id, price, currency,
                 observed_at, collected_at, metric_source, raw_source_record_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, platform, platform_product_id, observed_at) DO NOTHING
            """,
            (product_id, snap.source, snap.platform, snap.platform_product_id, snap.price,
             snap.currency, snap.observed_at, snap.collected_at, snap.metric_source, raw_id),
        )
    conn.commit()


def insert_sales_snapshot(conn: psycopg.Connection, product_id: int, snap: SalesSnapshot,
                          raw_id: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sales_snapshots
                (product_id, source, platform, platform_product_id, sales, review_count,
                 review_rating, observed_at, collected_at, metric_source, raw_source_record_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, platform, platform_product_id, observed_at) DO NOTHING
            """,
            (product_id, snap.source, snap.platform, snap.platform_product_id, snap.sales,
             snap.review_count, snap.review_rating, snap.observed_at, snap.collected_at,
             snap.metric_source, raw_id),
        )
    conn.commit()
