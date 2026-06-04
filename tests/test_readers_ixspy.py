from sourcing.readers.ixspy import read_ixspy


def test_ixspy_reader():
    products, prices = read_ixspy("tests/fixtures/ixspy_sample.csv", product_type="audio")
    assert len(products) == 1
    p = products[0]
    assert p.source == "ixspy"
    assert p.platform == "aliexpress"
    assert p.platform_product_id == "1005006"
    assert p.title == "Mini Speaker Pro"
    assert prices[0].price == 12.5
