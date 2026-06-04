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
