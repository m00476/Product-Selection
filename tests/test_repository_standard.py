def test_standard_tables_exist(conn):
    with conn.cursor() as cur:
        for table in ["products", "price_snapshots", "sales_snapshots",
                      "reviews", "erp_skus", "source_product_links"]:
            cur.execute("SELECT to_regclass(%s)", (table,))
            assert cur.fetchone()[0] is not None, table


def test_products_partial_unique_competitor_only(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('erp', NULL, 'own A', true)")
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('erp', NULL, 'own B', true)")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products WHERE is_own")
        assert cur.fetchone()[0] == 2
