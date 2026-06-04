from datetime import datetime, timezone
from sourcing.analysis.run import run_analysis


def _seed(conn):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon','500',false) RETURNING product_id")
        comp = cur.fetchone()[0]
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'seerfar','ozon','500',100.0,%s)", (comp, now))
        cur.execute("INSERT INTO sales_snapshots (product_id, source, platform, platform_product_id, sales, review_count, review_rating, observed_at) "
                    "VALUES (%s,'seerfar','ozon','500',2000,150,4.6,%s)", (comp, now))
        cur.execute("INSERT INTO products (platform, is_own) VALUES ('erp', true) RETURNING product_id")
        own = cur.fetchone()[0]
        cur.execute("INSERT INTO erp_skus (sku, own_product_id, cost_price) VALUES ('SKU1',%s,40.0)", (own,))
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'erp','erp',NULL,90.0,%s)", (own, now))
    conn.commit()
    return comp, own


def test_run_analysis_computes_both(conn):
    comp, own = _seed(conn)
    summary = run_analysis(conn)
    assert summary["profit_estimates"] == 2
    assert summary["opportunity_scores"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (own,))
        assert cur.fetchone()[0] == "high"
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (comp,))
        assert cur.fetchone()[0] == "low"
        cur.execute("SELECT score FROM opportunity_scores WHERE product_id=%s", (comp,))
        assert float(cur.fetchone()[0]) > 0
