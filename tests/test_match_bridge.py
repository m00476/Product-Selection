from datetime import datetime, timezone
from sourcing.bridge.match_reader import MatchRow
from sourcing.bridge.match_bridge import normalize_status, bridge_rows


def test_product_matches_table_exists(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('product_matches')")
        assert cur.fetchone()[0] is not None


def test_product_matches_upsert_by_unique_key(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon','900',false) RETURNING product_id")
        comp = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO product_matches (competitor_product_id, erp_sku, status, final_score) "
            "VALUES (%s,'SKU1','pending',10.0)", (comp,))
        cur.execute(
            "INSERT INTO product_matches (competitor_product_id, erp_sku, status, final_score) "
            "VALUES (%s,'SKU1','confirmed',20.0) "
            "ON CONFLICT (competitor_product_id, erp_sku) DO UPDATE SET "
            "status=EXCLUDED.status, final_score=EXCLUDED.final_score", (comp,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT status, final_score FROM product_matches WHERE competitor_product_id=%s", (comp,))
        assert cur.fetchone() == ("confirmed", 20.0)
        cur.execute("SELECT count(*) FROM product_matches")
        assert cur.fetchone()[0] == 1


def test_normalize_status():
    assert normalize_status("ERP里没有") == "no_erp_match"
    assert normalize_status("matched") == "confirmed"
    assert normalize_status("confirmed") == "confirmed"
    assert normalize_status("rejected") == "rejected"
    assert normalize_status(None) == "pending"
    assert normalize_status("weird") == "pending"


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon','900',false) RETURNING product_id")
        comp = cur.fetchone()[0]
        cur.execute("INSERT INTO products (platform, is_own) VALUES ('erp', true) RETURNING product_id")
        own = cur.fetchone()[0]
        cur.execute("INSERT INTO erp_skus (sku, own_product_id) VALUES ('SKU1',%s)", (own,))
    conn.commit()
    return comp, own


def test_bridge_rows_maps_and_links(conn):
    comp, own = _seed(conn)
    rows = [
        MatchRow("ozon", "900", "SKU1", 0.8, 0.7, 0.6, 0.5, 12.3, "matched"),
        MatchRow("ozon", "404", "SKUX", None, None, None, None, 1.0, "matched"),
    ]
    summary = bridge_rows(conn, rows)
    assert summary["bridged"] == 1
    assert summary["skipped_no_competitor"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT competitor_product_id, own_product_id, status, final_score "
                    "FROM product_matches")
        row = cur.fetchone()
        assert row[:3] == (comp, own, "confirmed")
        assert float(row[3]) == 12.3  # final_score 是 NUMERIC，按 float 比较


def test_bridge_no_erp_match_keeps_null_own(conn):
    comp, _ = _seed(conn)
    rows = [MatchRow("ozon", "900", "", None, None, None, None, 5.0, "ERP里没有")]
    bridge_rows(conn, rows)
    with conn.cursor() as cur:
        cur.execute("SELECT own_product_id, status FROM product_matches WHERE competitor_product_id=%s", (comp,))
        assert cur.fetchone() == (None, "no_erp_match")
