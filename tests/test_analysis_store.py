from datetime import datetime, timezone
from sourcing.analysis.store import (
    fetch_product_metrics, upsert_profit_estimate, upsert_opportunity_score,
)
from sourcing.analysis.profit import estimate_profit
from sourcing.analysis.scoring import score_opportunity


def test_analysis_tables_exist(conn):
    with conn.cursor() as cur:
        for table in ["profit_estimates", "opportunity_scores"]:
            cur.execute("SELECT to_regclass(%s)", (table,))
            assert cur.fetchone()[0] is not None, table


def test_profit_estimates_unique_product(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, is_own) VALUES ('ozon', false) RETURNING product_id")
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO profit_estimates (product_id, confidence) VALUES (%s, 'low')", (pid,))
        cur.execute(
            "INSERT INTO profit_estimates (product_id, confidence) VALUES (%s, 'high') "
            "ON CONFLICT (product_id) DO UPDATE SET confidence = EXCLUDED.confidence", (pid,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (pid,))
        assert cur.fetchone()[0] == "high"
        cur.execute("SELECT count(*) FROM profit_estimates")
        assert cur.fetchone()[0] == 1


def _seed_competitor(conn):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon', '500', false) RETURNING product_id")
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, "
                    "price, observed_at) VALUES (%s,'seerfar','ozon','500',100.0,%s)", (pid, now))
        cur.execute("INSERT INTO sales_snapshots (product_id, source, platform, platform_product_id, "
                    "sales, review_count, review_rating, observed_at) "
                    "VALUES (%s,'seerfar','ozon','500',2000,150,4.6,%s)", (pid, now))
    conn.commit()
    return pid


def test_fetch_product_metrics_returns_latest(conn):
    pid = _seed_competitor(conn)
    rows = fetch_product_metrics(conn)
    row = [r for r in rows if r["product_id"] == pid][0]
    assert row["is_own"] is False
    assert float(row["price"]) == 100.0
    assert float(row["sales"]) == 2000
    assert row["cost_price"] is None


def test_upsert_profit_and_opportunity(conn):
    pid = _seed_competitor(conn)
    est = estimate_profit(100.0, None, 0.30, estimated_purchase_cost=40.0)
    upsert_profit_estimate(conn, pid, est)
    upsert_profit_estimate(conn, pid, est)  # 幂等
    opp = score_opportunity(2000, est.margin, 4.6, 150)
    upsert_opportunity_score(conn, pid, opp)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM profit_estimates")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (pid,))
        assert cur.fetchone()[0] == "low"
        cur.execute("SELECT count(*) FROM opportunity_scores WHERE product_id=%s", (pid,))
        assert cur.fetchone()[0] == 1
