import json

from sourcing.collect import aliexpress_api_fetch


def test_flatten_aliexpress_record_builds_url_from_numeric_sku():
    row = aliexpress_api_fetch.flatten_aliexpress_record(
        {"productId": "1005012068000940", "productTitle": "Bag charm", "salePrice": "1.33"}
    )

    assert row["sku"] == "1005012068000940"
    assert row["product_url"] == "https://www.aliexpress.com/item/1005012068000940.html"


def test_flatten_aliexpress_record_exports_market_metrics():
    row = aliexpress_api_fetch.flatten_aliexpress_record(
        {
            "product_id": "1005012068000940",
            "product_name": "Home Fan",
            "product_price": "12.34",
            "trade_total": "321",
            "trade_7_count": "45",
            "review_total": "67",
            "ratings": "4.8",
            "store_name": "Home Store",
            "feedback": {"positive_rate": "96.5"},
        },
        source_rank=1,
    )

    assert row["sales"] == "321"
    assert row["sales_7d"] == "45"
    assert row["review_count"] == "67"
    assert row["rating"] == "4.8"
    assert row["seller_name"] == "Home Store"
    assert row["seller_positive_rate"] == "96.5"
    assert row["price"] == "12.34"


def test_validate_output_rows_rejects_empty_and_visible_fallback_rows():
    for rows in (
        [],
        [{"sku": "", "product_url": "", "price": "", "product_name": "visible card"}],
    ):
        try:
            aliexpress_api_fetch.validate_output_rows(rows)
        except RuntimeError as error:
            assert "AliExpress output quality check failed" in str(error)
        else:
            raise AssertionError("bad AliExpress rows were not rejected")


def test_load_product_request_uses_project_paths(tmp_path):
    candidate_dir = tmp_path / "output" / "aliexpress" / "bag_accessories"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "aliexpress_api_candidates.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://ixspy.com/goods-ranking",
                    "best_product_score": 20,
                    "best_record_count": 100,
                    "request": {
                        "method": "POST",
                        "url": "https://ixspy.com/goods-ranking",
                        "headers": {"Authorization": "redacted"},
                        "postData": '{"page":1,"limit":100}',
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    paths = aliexpress_api_fetch.ProjectPaths(tmp_path, "bag_accessories")
    request = aliexpress_api_fetch.load_product_request(paths)

    assert request.method == "POST"
    assert request.url == "https://ixspy.com/goods-ranking"
    assert paths.csv_file == tmp_path / "input" / "aliexpress" / "bag_accessories" / "aliexpress_products.csv"
