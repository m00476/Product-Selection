from sourcing.quality import inspect_csv_quality


def test_ixspy_quality_reports_missing_url_price_and_unknown_platform():
    report = inspect_csv_quality(
        "tests/fixtures/ixspy_missing_fields.csv",
        source="ixspy",
        product_type="bags",
    )

    assert report["source"] == "ixspy"
    assert report["product_type"] == "bags"
    assert report["total_rows"] == 2
    assert report["missing_product_url"] == 2
    assert report["missing_price"] == 2
    assert report["unknown_platform"] == 2
    assert report["fuzzy_pending"] == 2


def test_erp_quality_reports_missing_cost_and_stock():
    report = inspect_csv_quality(
        "tests/fixtures/erp_missing_cost.csv",
        source="erp",
        product_type="shopping_cart",
    )

    assert report["total_rows"] == 2
    assert report["missing_cost_price"] == 2
    assert report["missing_stock"] == 2


def test_seerfar_quality_accepts_complete_sample():
    report = inspect_csv_quality(
        "tests/fixtures/seerfar_sample.csv",
        source="seerfar",
        product_type="laptop",
    )

    assert report["total_rows"] == 2
    assert report["missing_product_url"] == 0
    assert report["missing_price"] == 0
    assert report["unknown_platform"] == 0
    assert report["deterministic"] == 2
