import os
import psycopg

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "migrations")


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, autocommit=False)


def migration_files() -> list[str]:
    names = [f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")]
    return [os.path.join(MIGRATIONS_DIR, n) for n in sorted(names)]


def run_migrations(conn: psycopg.Connection) -> None:
    for path in migration_files():
        with open(path, "r", encoding="utf-8") as fh:
            sql = fh.read()
        with conn.cursor() as cur:
            cur.execute(sql)
    conn.commit()
