from sourcing.importer import import_seerfar_csv


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
