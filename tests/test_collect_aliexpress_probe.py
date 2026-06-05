from sourcing.collect import aliexpress_api_probe


def test_build_candidates_prefers_product_like_api():
    responses = {
        "a": {
            "url": "https://ixspy.com/account/profile",
            "status": 200,
            "mimeType": "application/json",
            "record_lists": [{"path": "root.data", "count": 10, "product_score": 5, "sample": []}],
            "body_sample": "{}",
            "request": {"method": "GET", "url": "https://ixspy.com/account/profile"},
        },
        "b": {
            "url": "https://ixspy.com/goods-ranking",
            "status": 200,
            "mimeType": "application/json",
            "record_lists": [{"path": "root.data", "count": 100, "product_score": 20, "sample": []}],
            "body_sample": "{}",
            "request": {"method": "POST", "url": "https://ixspy.com/goods-ranking"},
        },
    }

    candidates = aliexpress_api_probe.build_candidates(responses)

    assert candidates[0]["url"] == "https://ixspy.com/goods-ranking"
    assert candidates[0]["best_record_count"] == 100


def test_probe_paths_are_project_local(tmp_path):
    paths = aliexpress_api_probe.ProjectPaths(tmp_path, "bag_accessories")

    assert paths.candidates_file == tmp_path / "output" / "aliexpress" / "bag_accessories" / "aliexpress_api_candidates.json"
    assert paths.visible_products_file == tmp_path / "output" / "aliexpress" / "bag_accessories" / "aliexpress_visible_products.csv"
