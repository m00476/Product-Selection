import uuid
import psycopg
import pytest
from sourcing import config, db


@pytest.fixture()
def conn():
    schema = "test_" + uuid.uuid4().hex[:12]
    connection = psycopg.connect(config.test_database_url(), autocommit=False)
    with connection.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    connection.commit()
    db.run_migrations(connection)
    try:
        yield connection
    finally:
        connection.rollback()
        with connection.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
        connection.commit()
        connection.close()
