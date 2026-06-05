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
