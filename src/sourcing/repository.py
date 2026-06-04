import hashlib
import json

import psycopg


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def insert_raw_record(conn: psycopg.Connection, *, source: str, platform: str,
                      product_type: str, source_file: str, source_record_id: str,
                      raw_payload: dict) -> int:
    """Append-only：内容变化才新增；与最新一条相同则返回其 id。"""
    payload_hash = _hash_payload(raw_payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, payload_hash FROM raw_source_records
            WHERE source=%s AND platform=%s AND source_record_id=%s
            ORDER BY collected_at DESC LIMIT 1
            """,
            (source, platform, source_record_id),
        )
        latest = cur.fetchone()
        if latest is not None and latest[1] == payload_hash:
            return latest[0]
        cur.execute(
            """
            INSERT INTO raw_source_records
                (source, platform, product_type, source_file, source_record_id,
                 raw_payload, payload_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (source, platform, product_type, source_file, source_record_id,
             json.dumps(raw_payload, ensure_ascii=False), payload_hash),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id
