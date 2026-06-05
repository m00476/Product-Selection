from sourcing.collect import erp_api_probe


def test_parse_category_path_supports_multiple_separators():
    assert erp_api_probe.parse_category_path("箱包 > 箱包配件") == ["箱包", "箱包配件"]
    assert erp_api_probe.parse_category_path("箱包/箱包配件") == ["箱包", "箱包配件"]


def test_filter_product_candidates_prefers_product_list_api():
    responses = {
        "1": {
            "url": "http://example.test/Api/shop/getAllShop",
            "status": 200,
            "mimeType": "application/json",
            "record_lists": [{"path": "root.data", "count": 999, "product_score": 20, "sample": []}],
            "body_sample": "{}",
            "request": {"method": "GET", "url": "http://example.test/Api/shop/getAllShop"},
        },
        "2": {
            "url": "http://example.test/Api/proudect/list",
            "status": 200,
            "mimeType": "application/json",
            "record_lists": [{"path": "root.data", "count": 100, "product_score": 80, "sample": []}],
            "body_sample": "{}",
            "request": {
                "method": "POST",
                "url": "http://example.test/Api/proudect/list",
                "postData": '{"status":"8","page":1,"limit":100,"isfile":0}',
            },
        },
    }

    candidates = erp_api_probe.build_candidates(responses)

    assert candidates[0]["url"] == "http://example.test/Api/proudect/list"
    assert candidates[0]["best_product_score"] == 80
