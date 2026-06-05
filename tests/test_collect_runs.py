from sourcing.collect.runs import (
    start_collector_run, finish_collector_run, record_collector_error,
)


def test_start_and_finish_run(conn):
    run_id = start_collector_run(conn, "seerfar", "laptop")
    assert isinstance(run_id, int)
    with conn.cursor() as cur:
        cur.execute("SELECT status, finished_at FROM collector_runs WHERE id=%s", (run_id,))
        status, finished = cur.fetchone()
        assert status == "running" and finished is None
    finish_collector_run(conn, run_id, status="success", record_count=5)
    with conn.cursor() as cur:
        cur.execute("SELECT status, record_count, finished_at FROM collector_runs WHERE id=%s", (run_id,))
        status, count, finished = cur.fetchone()
        assert status == "success" and count == 5 and finished is not None


def test_record_error(conn):
    run_id = start_collector_run(conn, "ozon", "laptop")
    record_collector_error(conn, run_id, "ozon", "boom", "stderr excerpt")
    with conn.cursor() as cur:
        cur.execute("SELECT run_id, source, detail, raw_excerpt FROM collector_errors WHERE run_id=%s", (run_id,))
        row = cur.fetchone()
        assert row == (run_id, "ozon", "boom", "stderr excerpt")
