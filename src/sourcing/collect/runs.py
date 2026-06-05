import psycopg


def start_collector_run(conn: psycopg.Connection, source: str, product_type: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO collector_runs (source, product_type, status) "
            "VALUES (%s, %s, 'running') RETURNING id",
            (source, product_type),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_collector_run(conn: psycopg.Connection, run_id: int, *,
                         status: str, record_count: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE collector_runs SET status=%s, record_count=%s, finished_at=now() WHERE id=%s",
            (status, record_count, run_id),
        )
    conn.commit()


def record_collector_error(conn: psycopg.Connection, run_id: int, source: str,
                           detail: str, raw_excerpt: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO collector_errors (run_id, source, detail, raw_excerpt) "
            "VALUES (%s, %s, %s, %s)",
            (run_id, source, detail, raw_excerpt),
        )
    conn.commit()
