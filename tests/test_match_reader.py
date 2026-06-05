import sqlite3
from sourcing.bridge.match_reader import read_match_results, MatchRow


def _make_app_db(path):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE match_results (
        id INTEGER PRIMARY KEY, platform TEXT, external_product_id TEXT,
        erp_sku TEXT, image_score REAL, title_score REAL, category_score REAL,
        price_score REAL, final_score REAL, match_status TEXT, fail_reason TEXT)""")
    c.execute("INSERT INTO match_results (platform, external_product_id, erp_sku, "
              "image_score, title_score, category_score, price_score, final_score, match_status) "
              "VALUES ('ozon','900','SKU1',0.8,0.7,0.6,0.5,12.3,'matched')")
    c.execute("INSERT INTO match_results (platform, external_product_id, erp_sku, "
              "final_score, match_status) VALUES ('aliexpress','1005','',5.0,'ERP里没有')")
    c.commit(); c.close()


def test_read_match_results(tmp_path):
    db = str(tmp_path / "app.db")
    _make_app_db(db)
    rows = read_match_results(db)
    assert len(rows) == 2
    assert isinstance(rows[0], MatchRow)
    assert rows[0].platform == "ozon"
    assert rows[0].external_product_id == "900"
    assert rows[0].erp_sku == "SKU1"
    assert rows[0].final_score == 12.3
    assert rows[0].match_status == "matched"
    assert rows[1].erp_sku == ""  # 空 sku 规范化为空串
    assert rows[1].match_status == "ERP里没有"
