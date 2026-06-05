import psycopg

from sourcing.erp_image_search import (
    output_csv_path, _read_csv_dicts, build_boss_decision_rows,
)


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert_image_decision(conn: psycopg.Connection, d: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO erp_image_decisions
                (source, product_type, external_sku, external_product_name,
                 external_product_url, external_image_url, final_decision, boss_action,
                 candidate_count, normal_candidate_count, stopped_candidate_count,
                 limited_candidate_count, risk_candidate_count, top_erp_skus, top_main_skus)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, product_type, external_sku) DO UPDATE SET
                external_product_name=EXCLUDED.external_product_name,
                external_product_url=EXCLUDED.external_product_url,
                external_image_url=EXCLUDED.external_image_url,
                final_decision=EXCLUDED.final_decision, boss_action=EXCLUDED.boss_action,
                candidate_count=EXCLUDED.candidate_count,
                normal_candidate_count=EXCLUDED.normal_candidate_count,
                stopped_candidate_count=EXCLUDED.stopped_candidate_count,
                limited_candidate_count=EXCLUDED.limited_candidate_count,
                risk_candidate_count=EXCLUDED.risk_candidate_count,
                top_erp_skus=EXCLUDED.top_erp_skus, top_main_skus=EXCLUDED.top_main_skus,
                generated_at=now()
            """,
            (
                d.get("source"), d.get("product_type"), d.get("external_sku"),
                d.get("external_product_name"), d.get("external_product_url"),
                d.get("external_image_url"), d.get("final_decision"), d.get("boss_action"),
                _to_int(d.get("candidate_count")), _to_int(d.get("normal_candidate_count")),
                _to_int(d.get("stopped_candidate_count")), _to_int(d.get("limited_candidate_count")),
                _to_int(d.get("risk_candidate_count")), d.get("top_erp_skus"), d.get("top_main_skus"),
            ),
        )
    conn.commit()


def load_image_decisions(conn: psycopg.Connection, *, source: str, product_type: str,
                         base_dir: str) -> dict:
    rows = _read_csv_dicts(output_csv_path(base_dir, source, product_type))
    decisions = build_boss_decision_rows(rows)
    for d in decisions:
        upsert_image_decision(conn, d)
    return {"loaded": len(decisions)}
