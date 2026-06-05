from datetime import datetime, timezone


def _seed(conn):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('ozon','900','Comp A',false) RETURNING product_id")
        a = cur.fetchone()[0]
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'seerfar','ozon','900',100.0,%s)", (a, now))
        cur.execute("INSERT INTO sales_snapshots (product_id, source, platform, platform_product_id, sales, review_rating, observed_at) "
                    "VALUES (%s,'seerfar','ozon','900',500,4.5,%s)", (a, now))
        cur.execute("INSERT INTO opportunity_scores (product_id, score, reason) VALUES (%s,0.42,'r')", (a,))
        cur.execute("INSERT INTO product_matches (competitor_product_id, erp_sku, status) VALUES (%s,'S1','no_erp_match')", (a,))
        cur.execute("INSERT INTO product_matches (competitor_product_id, erp_sku, status) VALUES (%s,'S2','no_erp_match')", (a,))
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('ozon','901','Comp B',false) RETURNING product_id")
        b = cur.fetchone()[0]
        cur.execute("INSERT INTO products (platform, title, is_own) VALUES ('erp','Own X',true) RETURNING product_id")
        own = cur.fetchone()[0]
        cur.execute("INSERT INTO erp_skus (sku, own_product_id, cost_price) VALUES ('SKUOWN',%s,30.0)", (own,))
        cur.execute("INSERT INTO product_matches (competitor_product_id, own_product_id, erp_sku, status, final_score) "
                    "VALUES (%s,%s,'SKUOWN','confirmed',55.0)", (b, own))
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'seerfar','ozon','901',88.0,%s)", (b, now))
    conn.commit()
    return a, b, own


def test_v_opportunities_one_row_per_competitor_and_gap(conn):
    a, b, _ = _seed(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT product_id, opportunity_score, latest_price, latest_sales, is_gap "
                    "FROM v_opportunities WHERE product_id=%s", (a,))
        rows = cur.fetchall()
        assert len(rows) == 1
        pid, score, price, sales, is_gap = rows[0]
        assert float(score) == 0.42
        assert float(price) == 100.0
        assert float(sales) == 500
        assert is_gap is True
        cur.execute("SELECT is_gap FROM v_opportunities WHERE product_id=%s", (b,))
        assert cur.fetchone()[0] is False


def test_v_competitor_monitor_shows_confirmed_pairs(conn):
    a, b, own = _seed(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT own_product_id, own_sku, cost_price, competitor_product_id, "
                    "competitor_price, final_score FROM v_competitor_monitor")
        rows = cur.fetchall()
    assert len(rows) == 1
    own_id, sku, cost, comp_id, comp_price, score = rows[0]
    assert own_id == own and sku == "SKUOWN" and comp_id == b
    assert float(comp_price) == 88.0 and float(score) == 55.0
