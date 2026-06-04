from sourcing.contracts import NormalizedProduct
from sourcing.repository import upsert_product, link_source_record


def _product(source):
    return NormalizedProduct(source=source, platform="aliexpress",
                             platform_product_id="1005006", canonical_url="c",
                             source_record_id="1005006", product_type="audio",
                             title=f"from-{source}")


def test_two_sources_same_id_link_to_one_product(conn):
    seerfar = _product("seerfar")
    ixspy = _product("ixspy")
    pid_a = upsert_product(conn, seerfar)
    pid_b = upsert_product(conn, ixspy)
    assert pid_a == pid_b  # 同 (platform, platform_product_id) -> 同一 product

    link_source_record(conn, seerfar, product_id=pid_a, raw_id=None)
    link_source_record(conn, ixspy, product_id=pid_b, raw_id=None)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_product_links WHERE product_id=%s", (pid_a,))
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(DISTINCT source) FROM source_product_links")
        assert cur.fetchone()[0] == 2


def test_link_upsert_by_source_record(conn):
    seerfar = _product("seerfar")
    pid = upsert_product(conn, seerfar)
    link_source_record(conn, seerfar, product_id=pid, raw_id=None)
    link_source_record(conn, seerfar, product_id=pid, raw_id=None)  # 重复
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_product_links")
        assert cur.fetchone()[0] == 1
