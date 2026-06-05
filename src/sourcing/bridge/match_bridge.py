from decimal import Decimal

import psycopg
from psycopg.types.numeric import NumericLoader
from sourcing.bridge.match_reader import MatchRow


class _FloatNumericLoader(NumericLoader):
    """Load PostgreSQL NUMERIC as float so scores round-trip as Python floats."""

    def load(self, data):
        value = super().load(data)
        return float(value) if isinstance(value, Decimal) else value


# NUMERIC oid = 1700; register globally so final_score etc. come back as float.
psycopg.adapters.register_loader("numeric", _FloatNumericLoader)


def normalize_status(raw: str | None) -> str:
    if not raw:
        return "pending"
    text = raw.strip().lower()
    if "没有" in raw or "no" in text:
        return "no_erp_match"
    if "confirm" in text or "match" in text:
        return "confirmed"
    if "reject" in text:
        return "rejected"
    return "pending"


def _find_competitor(conn, platform, external_product_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT product_id FROM products "
            "WHERE is_own = false AND platform = %s AND platform_product_id = %s",
            (platform, external_product_id),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _find_own(conn, erp_sku):
    if not erp_sku:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT own_product_id FROM erp_skus WHERE sku = %s", (erp_sku,))
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else None


def bridge_rows(conn: psycopg.Connection, rows: list[MatchRow]) -> dict:
    bridged = 0
    skipped = 0
    for r in rows:
        competitor_id = _find_competitor(conn, r.platform, r.external_product_id)
        if competitor_id is None:
            skipped += 1
            continue
        own_id = _find_own(conn, r.erp_sku)
        status = normalize_status(r.match_status)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO product_matches
                    (competitor_product_id, own_product_id, erp_sku, match_source,
                     image_score, title_score, category_score, price_score, final_score,
                     raw_match_status, status)
                VALUES (%s,%s,%s,'518',%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (competitor_product_id, erp_sku) DO UPDATE SET
                    own_product_id=EXCLUDED.own_product_id,
                    image_score=EXCLUDED.image_score, title_score=EXCLUDED.title_score,
                    category_score=EXCLUDED.category_score, price_score=EXCLUDED.price_score,
                    final_score=EXCLUDED.final_score, raw_match_status=EXCLUDED.raw_match_status,
                    status=EXCLUDED.status, bridged_at=now()
                """,
                (competitor_id, own_id, r.erp_sku, r.image_score, r.title_score,
                 r.category_score, r.price_score, r.final_score, r.match_status, status),
            )
        bridged += 1
    conn.commit()
    return {"bridged": bridged, "skipped_no_competitor": skipped}
