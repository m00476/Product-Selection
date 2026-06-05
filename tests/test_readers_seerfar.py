from sourcing.readers.seerfar import read_seerfar


def test_seerfar_reader_maps_fields_and_platform():
    products, prices, sales = read_seerfar("tests/fixtures/seerfar_sample.csv", product_type="laptop")
    assert len(products) == 2
    ozon = products[0]
    assert ozon.source == "seerfar"
    assert ozon.platform == "ozon"
    assert ozon.platform_product_id == "3637903008"
    assert ozon.canonical_url == "https://www.ozon.ru/product/3637903008"
    assert ozon.title == "ASUS Zenbook 14"

    ae = products[1]
    assert ae.platform == "aliexpress"
    assert ae.platform_product_id == "1005006"

    assert prices[0].price == 91510.0
    assert prices[0].metric_source == "seerfar"
    assert sales[0].sales == 553
    assert sales[0].review_count == 28


def test_seerfar_reader_keeps_extended_estimated_metrics():
    products, _prices, sales = read_seerfar(
        "tests/fixtures/seerfar_extended_sample.csv",
        product_type="training_mask",
    )

    product = products[0]
    assert product.extra_metrics["gross_margin"] == 54.9
    assert product.extra_metrics["views"] == 3804
    assert product.extra_metrics["order_conversion_rate"] == 41.2
    assert sales[0].metric_source == "seerfar"
