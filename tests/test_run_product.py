from sourcing.run_product import run_product


def _fake_collect_ok(conn, source, product_type, *, base_dir):
    return {"status": "success", "source": source, "product_type": product_type, "records": 30}


def _fake_collect_fail(conn, source, product_type, *, base_dir):
    return {"status": "failed", "source": source, "product_type": product_type}


def _fake_pipeline(conn, *, source, product_type, base_dir, limit, threshold):
    return {"reranked": 30, "confident": 8}


def test_collect_failure_skips_pipeline_and_reports_failed():
    pipeline_calls = []
    def pipeline(conn, **kw):
        pipeline_calls.append(kw)
        return {}
    result = run_product(None, source="ixspy", product_type="x", base_dir="b",
                         env={}, collect=_fake_collect_fail, pipeline=pipeline, emit=lambda m: None)
    assert result["status"] == "failed"
    assert result["stage"] == "collect"
    assert pipeline_calls == []  # 采集失败绝不往下跑


def test_success_runs_pipeline_and_returns_both_summaries():
    result = run_product(None, source="ixspy", product_type="x", base_dir="b",
                         env={}, collect=_fake_collect_ok, pipeline=_fake_pipeline, emit=lambda m: None)
    assert result["status"] == "success"
    assert result["collect"]["records"] == 30
    assert result["pipeline"]["confident"] == 8


def test_sets_category_and_headless_into_env_before_collect():
    seen = {}
    def collect(conn, source, product_type, *, base_dir):
        seen["category"] = env.get("ALIEXPRESS_CATEGORY_NAME")
        seen["headless"] = env.get("SCRAPER_HEADLESS")
        return {"status": "success", "records": 1}
    env = {}
    run_product(None, source="ixspy", product_type="x", base_dir="b", env=env,
                category="园林工具", headless=True,
                collect=collect, pipeline=_fake_pipeline, emit=lambda m: None)
    # 采集子进程靠 env 读类目/headless，必须在 collect 前写好
    assert seen["category"] == "园林工具"
    assert seen["headless"] == "1"


def test_emits_log_lines_for_each_stage():
    lines = []
    run_product(None, source="ixspy", product_type="x", base_dir="b", env={},
                collect=_fake_collect_ok, pipeline=_fake_pipeline, emit=lines.append)
    text = "\n".join(lines)
    assert "collect" in text.lower()
    assert "pipeline" in text.lower()
