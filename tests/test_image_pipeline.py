import sourcing.erp_image_pipeline as pipe


def test_run_pipeline_chains_four_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(pipe, "run_image_search",
                        lambda **k: calls.append(("search", k)) or {"searched": 5})
    monkeypatch.setattr(pipe, "rerank_image_search",
                        lambda **k: calls.append(("rerank", k)) or {"reranked": 5, "confident": 2})
    monkeypatch.setattr(pipe, "load_image_decisions",
                        lambda conn, **k: calls.append(("load", k)) or {"loaded": 3})
    monkeypatch.setattr(pipe, "generate_boss_decision_report",
                        lambda **k: calls.append(("report", k)) or {"products": 3})
    monkeypatch.setattr(pipe, "generate_best_match_report",
                        lambda **k: calls.append(("best_match", k)) or {"products": 3})
    out = pipe.run_pipeline(object(), source="ixspy", product_type="bags",
                            base_dir="/b", limit=5, threshold=0.8)
    assert [c[0] for c in calls] == ["search", "rerank", "load", "report", "best_match"]
    assert out["search"] == {"searched": 5}
    assert out["report"] == {"products": 3}
    assert out["best_match"] == {"products": 3}
    assert calls[0][1]["limit"] == 5            # search 收到 limit
    assert calls[1][1]["threshold"] == 0.8      # rerank 收到 threshold
    assert calls[2][1] == {"source": "ixspy", "product_type": "bags", "base_dir": "/b"}
