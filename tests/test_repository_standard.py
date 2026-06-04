from datetime import datetime, timezone
from sourcing.contracts import NormalizedProduct, PriceSnapshot
from sourcing.repository import upsert_product, insert_price_snapshot


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


def test_upsert_product_competitor_idempotent(conn):
    p = NormalizedProduct(source="seerfar", platform="ozon", platform_product_id="900",
                          canonical_url="u", source_record_id="900", product_type="t",
                          title="X")
    id1 = upsert_product(conn, p)
    id2 = upsert_product(conn, p)  # 同竞品再来一次
    assert id1 == id2  # 命中部分唯一索引 -> 同一行
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products")
        assert cur.fetchone()[0] == 1


def test_price_snapshot_unique_observed_at(conn):
    now = datetime.now(timezone.utc)
    p = NormalizedProduct(source="seerfar", platform="ozon", platform_product_id="901",
                          canonical_url="u", source_record_id="901", product_type="t")
    pid = upsert_product(conn, p)
    snap = PriceSnapshot(source="seerfar", platform="ozon", platform_product_id="901",
                         price=10.0, currency="RUB", observed_at=now, collected_at=now,
                         metric_source="seerfar")
    insert_price_snapshot(conn, pid, snap)
    insert_price_snapshot(conn, pid, snap)  # 同 observed_at -> upsert 不新增
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM price_snapshots")
        assert cur.fetchone()[0] == 1
