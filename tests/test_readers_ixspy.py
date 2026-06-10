from sourcing.readers.ixspy import read_ixspy


def test_ixspy_reader():
    products, prices, sales = read_ixspy("tests/fixtures/ixspy_sample.csv", product_type="audio")
    assert len(products) == 1
    p = products[0]
    assert p.source == "ixspy"
    assert p.platform == "aliexpress"
    assert p.platform_product_id == "1005006"
    assert p.title == "Mini Speaker Pro"
    assert p.image_url == "https://img/y.jpg"
    assert p.seller_id == "777"
    assert p.seller_name == "ShopX"
    assert p.extra_metrics["weekly_growth"] == "120"
    assert p.extra_metrics["first_found_at"] == "2026-04-20"
    assert p.extra_metrics["avg_daily_sales_1y"] == "5"
    assert p.extra_metrics["fulfillment_type"] == "半托管"
    assert prices[0].price == 12.5
    assert sales[0].sales == 2000
    assert sales[0].review_count == 50
    assert sales[0].review_rating == 4.6
