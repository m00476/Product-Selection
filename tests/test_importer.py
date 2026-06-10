from sourcing.importer import import_seerfar_csv
from sourcing.importer import import_erp_csv, import_ixspy_csv


def test_import_seerfar_end_to_end(conn):
    summary = import_seerfar_csv(conn, "tests/fixtures/seerfar_sample.csv",
                                 product_type="laptop",
                                 source_file="input/seerfar/laptop/seerfar_products.csv")
    assert summary["products"] == 2
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM price_snapshots")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM sales_snapshots")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM source_product_links WHERE link_type='deterministic'")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM raw_source_records")
        assert cur.fetchone()[0] == 2


def test_import_three_sources_end_to_end(conn):
    import_seerfar_csv(conn, "tests/fixtures/seerfar_sample.csv",
                       product_type="audio",
                       source_file="input/seerfar/audio/seerfar_products.csv")
    import_ixspy_csv(conn, "tests/fixtures/ixspy_sample.csv",
                     product_type="audio",
                     source_file="input/aliexpress/audio/aliexpress_products.csv")
    import_erp_csv(conn, "tests/fixtures/erp_sample.csv",
                   product_type="socks",
                   source_file="input/erp/socks/erp_products.csv")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT product_id FROM products "
            "WHERE platform='aliexpress' AND platform_product_id='1005006'"
        )
        ali_product_id = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM source_product_links "
            "WHERE product_id=%s AND source IN ('seerfar', 'ixspy')",
            (ali_product_id,),
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT sales, review_count, review_rating FROM sales_snapshots "
            "WHERE product_id=%s AND source='ixspy'",
            (ali_product_id,),
        )
        ixspy_sales, ixspy_reviews, ixspy_rating = cur.fetchone()
        assert float(ixspy_sales) == 2000
        assert ixspy_reviews == 50
        assert float(ixspy_rating) == 4.6

        cur.execute("SELECT count(*) FROM products WHERE is_own=true")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT cost_price, stock FROM erp_skus WHERE sku='G-SH-WAC-225'")
        cost_price, stock = cur.fetchone()
        assert float(cost_price) == 1.8361
        assert stock == 100

        cur.execute(
            "SELECT raw_payload FROM raw_source_records "
            "WHERE source='seerfar' AND source_record_id='1005006'"
        )
        raw_payload = cur.fetchone()[0]
        assert raw_payload["sales"] == "2000"
        assert raw_payload["price"] == "12.5"
