from sourcing.collect import seerfar_api_probe


def test_parse_category_path_supports_multiple_separators():
    assert seerfar_api_probe.parse_category_path("运动 > 训练面罩") == ["运动", "训练面罩"]
    assert seerfar_api_probe.parse_category_path("运动/训练面罩") == ["运动", "训练面罩"]


def test_build_candidates_prefers_product_search_api():
    responses = {
        "a": {
            "url": "https://seerfar.cn/api/account/profile",
            "status": 200,
            "mimeType": "application/json",
            "record_lists": [{"path": "root.data", "count": 10, "product_score": 5, "sample": []}],
            "body_sample": "{}",
            "request": {"method": "GET", "url": "https://seerfar.cn/api/account/profile"},
        },
        "b": {
            "url": "https://seerfar.cn/api/product-report/product/search",
            "status": 200,
            "mimeType": "application/json",
            "record_lists": [{"path": "root.data", "count": 100, "product_score": 80, "sample": []}],
            "body_sample": "{}",
            "request": {"method": "POST", "url": "https://seerfar.cn/api/product-report/product/search"},
        },
    }

    candidates = seerfar_api_probe.build_candidates(responses)

    assert candidates[0]["url"] == "https://seerfar.cn/api/product-report/product/search"
    assert candidates[0]["best_record_count"] == 100
