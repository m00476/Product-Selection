import json
from sourcing.erp_token import extract_erp_token, refresh_erp_token


def test_extract_erp_token(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([
        {"request": {"headers": {"X-A": "1"}}},
        {"request": {"headers": {"Authorization": "eyJ.tok.en"}}},
    ]), encoding="utf-8")
    assert extract_erp_token(str(p)) == "eyJ.tok.en"


def test_extract_erp_token_missing(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("[]", encoding="utf-8")
    assert extract_erp_token(str(p)) is None
    assert extract_erp_token(str(tmp_path / "nope.json")) is None


def test_refresh_erp_token_runs_probe_then_extracts(tmp_path, monkeypatch):
    base = str(tmp_path)
    # 假 runner：模拟 probe 写出 candidates
    cand_dir = tmp_path / "output" / "erp" / "token_refresh"
    class FakeRunner:
        def run(self, args, *, cwd, env):
            cand_dir.mkdir(parents=True, exist_ok=True)
            (cand_dir / "erp_api_candidates.json").write_text(
                json.dumps([{"request": {"headers": {"Authorization": "fresh.tok"}}}]), encoding="utf-8")
            self.env = env
            class R: returncode=0; stdout="ok"; stderr=""
            return R()
    monkeypatch.delenv("ERP_IMAGE_SEARCH_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = FakeRunner()
    token = refresh_erp_token(base, runner=runner)
    assert token == "fresh.tok"
    import os
    assert os.environ["ERP_IMAGE_SEARCH_TOKEN"] == "fresh.tok"     # 更新了进程env
    assert runner.env["COLLECT_OUTPUT_ROOT"] == base               # probe写到base_dir


def test_run_image_search_auto_refreshes_on_token_expiry(tmp_path):
    import csv
    from pathlib import Path
    from sourcing.erp_image_search import run_image_search, SearchResult, output_csv_path
    base = str(tmp_path)
    # 准备输入 CSV(ixspy -> input/aliexpress/pt/aliexpress_products.csv)
    inp = Path(base) / "input" / "aliexpress" / "pt" / "aliexpress_products.csv"
    inp.parent.mkdir(parents=True, exist_ok=True)
    with open(inp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sku", "product_name", "image_url"])
        w.writeheader(); w.writerow({"sku": "E1", "product_name": "A", "image_url": "http://x/a.jpg"})

    state = {"refreshed": False}
    def fake_search(url):
        if not state["refreshed"]:
            return SearchResult(status="error", code=404, message="Not Found", trace_id="", matches=[], raw={})
        return SearchResult(status="success", code=200, message="", trace_id="",
                            matches=[{"matched_erp_sku": "ERP1", "erp_image_url": "e1"}], raw={})
    def fake_refresher(base_dir):
        state["refreshed"] = True
        return "newtok"

    run_image_search(source="ixspy", product_type="pt", base_dir=base,
                     search_func=fake_search, token_refresher=fake_refresher, delay_seconds=0)
    rows = list(csv.DictReader(open(output_csv_path(base, "ixspy", "pt"), encoding="utf-8-sig")))
    # 刷新后重试成功 -> 落到匹配结果
    assert rows[0]["matched_erp_sku"] == "ERP1"
    assert rows[0]["match_status"] == "success"
