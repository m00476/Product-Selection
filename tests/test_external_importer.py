import sqlite3

from sourcing.bridge.external_importer import (
    read_external_products, import_external_products,
)


def _make_app_db(path):
    c = sqlite3.connect(path)
    c.execute(
        """CREATE TABLE external_products (
            id INTEGER PRIMARY KEY, platform TEXT, external_product_id TEXT,
            title TEXT, category TEXT, price REAL, main_image_url TEXT,
            product_url TEXT, sales TEXT)"""
    )
    c.execute(
        "INSERT INTO external_products (platform, external_product_id, title, category, "
        "price, main_image_url, product_url, sales) VALUES "
        "('seerfar','3658315060','Ozon chair','furniture',602.0,'http://img/a.jpg',"
        "'https://www.ozon.ru/product/3658315060','356')"
    )
    # 无法解析出市场ID的行 -> 应跳过
    c.execute(
        "INSERT INTO external_products (platform, external_product_id, title, product_url) "
        "VALUES ('seerfar','x','no url','')"
    )
    c.commit()
    c.close()


def test_read_external_products(tmp_path):
    db = str(tmp_path / "app.db")
    _make_app_db(db)
    rows = read_external_products(db)
    assert len(rows) == 2
    assert rows[0]["external_product_id"] == "3658315060"
    assert rows[0]["product_url"].endswith("3658315060")


def test_import_external_products_into_pg(conn, tmp_path):
    db = str(tmp_path / "app.db")
    _make_app_db(db)
    summary = import_external_products(conn, db)
    assert summary["imported"] == 1
    assert summary["skipped_no_id"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT platform, platform_product_id, title, is_own FROM products")
        assert cur.fetchone() == ("ozon", "3658315060", "Ozon chair", False)
        cur.execute("SELECT price FROM price_snapshots WHERE platform_product_id='3658315060'")
        assert float(cur.fetchone()[0]) == 602.0
        cur.execute("SELECT sales FROM sales_snapshots WHERE platform_product_id='3658315060'")
        assert float(cur.fetchone()[0]) == 356.0
        cur.execute("SELECT link_type FROM source_product_links WHERE source='518'")
        assert cur.fetchone()[0] == "deterministic"
