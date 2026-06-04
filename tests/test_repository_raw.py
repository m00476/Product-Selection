import json

from sourcing.repository import insert_raw_record


def test_raw_tables_exist(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw_source_records')")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regclass('collector_runs')")
        assert cur.fetchone()[0] is not None


def test_raw_unique_key_includes_collected_at(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE tablename = 'raw_source_records' AND indexdef ILIKE '%unique%'
            """
        )
        defs = " ".join(row[0] for row in cur.fetchall()).lower()
    assert "collected_at" in defs and "source_record_id" in defs and "platform" in defs


def test_insert_raw_dedupes_identical_payload(conn):
    payload = {"sku": "1", "price": 10}
    first = insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                              source_file="input/seerfar/t/x.csv", source_record_id="1",
                              raw_payload=payload)
    second = insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                               source_file="input/seerfar/t/x.csv", source_record_id="1",
                               raw_payload=payload)
    assert second == first  # 内容相同 -> 返回已有 id，不新增
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_source_records WHERE source_record_id='1'")
        assert cur.fetchone()[0] == 1


def test_insert_raw_keeps_history_on_change(conn):
    insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                      source_file="f", source_record_id="2", raw_payload={"price": 10})
    insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                      source_file="f", source_record_id="2", raw_payload={"price": 11})
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_source_records WHERE source_record_id='2'")
        assert cur.fetchone()[0] == 2  # 内容变化 -> 保留历史
