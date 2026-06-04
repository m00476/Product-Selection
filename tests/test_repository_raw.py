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
