from sourcing.erp_image_search import build_best_match_rows, best_match_verdict


def test_best_match_verdict_thresholds():
    assert best_match_verdict(0.9) == "高置信匹配"
    assert best_match_verdict(0.75) == "可能匹配"
    assert best_match_verdict(0.55) == "弱匹配(需人工)"
    assert best_match_verdict(0.2) == "无匹配(疑似不同款)"
    assert best_match_verdict(-1) == "无图(竞品图失败)"


def test_build_best_match_picks_highest_and_keeps_candidate():
    rows = [
        {"external_sku": "E1", "external_product_name": "Comp A", "external_image_url": "qa",
         "matched_erp_sku": "ERP_low", "erp_image_url": "erp_low",
         "erp_product_status_text": "正常商品", "embedding_similarity": "0.40"},
        {"external_sku": "E1", "external_product_name": "Comp A", "external_image_url": "qa",
         "matched_erp_sku": "ERP_high", "erp_image_url": "erp_high",
         "erp_product_status_text": "正常商品", "embedding_similarity": "0.92"},
        {"external_sku": "E2", "external_product_name": "Comp B", "external_image_url": "qb",
         "matched_erp_sku": "ERP_x", "erp_image_url": "erp_x",
         "erp_product_status_text": "停产商品", "embedding_similarity": "0.30"},
    ]
    out = build_best_match_rows(rows)
    assert len(out) == 2
    e1 = [r for r in out if r["竞品SKU"] == "E1"][0]
    assert e1["最像ERP_SKU"] == "ERP_high"
    assert e1["ERP候选图"] == "erp_high"
    assert e1["匹配判定"] == "高置信匹配"
    e2 = [r for r in out if r["竞品SKU"] == "E2"][0]
    assert e2["最像ERP_SKU"] == "ERP_x"          # B口径: 无匹配也保留最像候选
    assert e2["ERP候选图"] == "erp_x"
    assert e2["匹配判定"] == "无匹配(疑似不同款)"
