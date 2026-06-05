import json

from sourcing.collect import seerfar_api_fetch


def test_flatten_seerfar_record_exports_market_metrics():
    row = seerfar_api_fetch.flatten_seerfar_record(
        {
            "sku": "ozon-1",
            "title": "Training mask",
            "brandName": "Brand",
            "imageUrl": "https://example.test/image.jpg",
            "productUrl": "https://www.ozon.ru/product/123",
            "price": "99.5",
            "sales": 88,
            "reviewCount": 12,
            "reviewRating": 4.7,
            "categoryInfo": {
                "cnTitlePath": "运动 > 训练面罩",
                "enTitlePath": "Sports > Training Mask",
                "category": {"id": 123, "cnTitle": "训练面罩"},
            },
        },
        1,
    )

    assert row["sku"] == "ozon-1"
    assert row["product_name"] == "Training mask"
    assert row["price"] == "99.5"
    assert row["sales"] == "88"
    assert row["review_count"] == "12"
    assert row["review_rating"] == "4.7"
    assert "训练面罩" in row["category"]


def test_validate_output_rows_rejects_empty_or_unusable_rows():
    for rows in (
        [],
        [{"sku": "", "product_url": "", "price": "", "product_name": ""}],
    ):
        try:
            seerfar_api_fetch.validate_output_rows(rows)
        except RuntimeError as error:
            assert "Seerfar output quality check failed" in str(error)
        else:
            raise AssertionError("bad Seerfar rows were not rejected")


def test_load_product_request_uses_project_paths(tmp_path):
    candidate_dir = tmp_path / "output" / "seerfar" / "training_mask"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "seerfar_api_candidates.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://seerfar.cn/api/product-report/product/search",
                    "best_product_score": 80,
                    "best_record_count": 100,
                    "request": {
                        "method": "POST",
                        "url": "https://seerfar.cn/api/product-report/product/search",
                        "headers": {"Authorization": "redacted"},
                        "postData": '{"page":{"pageNumber":1,"pageSize":100}}',
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    paths = seerfar_api_fetch.ProjectPaths(tmp_path, "training_mask")
    request = seerfar_api_fetch.load_product_request(paths)

    assert request.method == "POST"
    assert "product-report/product/search" in request.url
    assert paths.csv_file == tmp_path / "input" / "seerfar" / "training_mask" / "seerfar_products.csv"
