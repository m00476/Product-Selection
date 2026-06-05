import psycopg
from sourcing.bridge.match_reader import read_match_results
from sourcing.bridge.match_bridge import bridge_rows


def bridge_matches(conn: psycopg.Connection, app_db_path: str) -> dict:
    rows = read_match_results(app_db_path)
    summary = bridge_rows(conn, rows)
    summary["read"] = len(rows)
    return summary
