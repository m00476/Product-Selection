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
