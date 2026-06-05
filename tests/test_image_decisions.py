import csv
from pathlib import Path
from sourcing.bridge.image_decisions import load_image_decisions
from sourcing.erp_image_search import output_csv_path, RESULT_FIELDS


def test_image_decisions_table_and_view_exist(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('erp_image_decisions')")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regclass('v_erp_image_decisions')")
        assert cur.fetchone()[0] is not None


def test_image_decisions_unique_and_view_flag(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO erp_image_decisions (source, product_type, external_sku, final_decision) "
            "VALUES ('ixspy','bags','S1','疑似新品机会')")
        cur.execute(
            "INSERT INTO erp_image_decisions (source, product_type, external_sku, final_decision) "
            "VALUES ('ixspy','bags','S1','疑似已有正常同款') "
            "ON CONFLICT (source, product_type, external_sku) DO UPDATE SET "
            "final_decision=EXCLUDED.final_decision")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM erp_image_decisions")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT final_decision, is_new_opportunity FROM v_erp_image_decisions WHERE external_sku='S1'")
        decision, is_opp = cur.fetchone()
        assert decision == "疑似已有正常同款"
        assert is_opp is False


def _write_results_csv(base_dir, source, product_type, rows):
    path = output_csv_path(base_dir, source, product_type)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})


def test_load_image_decisions(conn, tmp_path):
    base = str(tmp_path)
    rows = [
        {"source": "ixspy", "product_type": "bags", "external_sku": "E1",
         "external_product_name": "Bag A", "matched_erp_sku": "ERP1",
         "match_status": "success", "erp_product_status": "8",
         "candidate_priority": "可用正常商品"},
        {"source": "ixspy", "product_type": "bags", "external_sku": "E1",
         "external_product_name": "Bag A", "matched_erp_sku": "ERP2",
         "match_status": "success", "erp_product_status": "8",
         "candidate_priority": "可用正常商品"},
        {"source": "ixspy", "product_type": "bags", "external_sku": "E2",
         "external_product_name": "Bag B", "matched_erp_sku": "",
         "match_status": "empty", "erp_product_status": "",
         "candidate_priority": "需人工确认"},
    ]
    _write_results_csv(base, "ixspy", "bags", rows)
    summary = load_image_decisions(conn, source="ixspy", product_type="bags", base_dir=base)
    assert summary["loaded"] == 2
    with conn.cursor() as cur:
        cur.execute("SELECT final_decision, normal_candidate_count FROM erp_image_decisions WHERE external_sku='E1'")
        assert cur.fetchone() == ("疑似已有正常同款", 2)
        cur.execute("SELECT is_new_opportunity FROM v_erp_image_decisions WHERE external_sku='E2'")
        assert cur.fetchone()[0] is True
    load_image_decisions(conn, source="ixspy", product_type="bags", base_dir=base)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM erp_image_decisions")
        assert cur.fetchone()[0] == 2
