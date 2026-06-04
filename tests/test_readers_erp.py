from sourcing.readers.erp import read_erp


def test_erp_reader_marks_own_and_cost():
    products, skus = read_erp("tests/fixtures/erp_sample.csv", product_type="socks")
    assert len(products) == 1
    p = products[0]
    assert p.is_own is True
    assert p.platform == "erp"
    assert p.platform_product_id is None  # 自家商品无竞品平台ID
    assert p.title == "半截隐形袜"
    s = skus[0]
    assert s["sku"] == "G-SH-WAC-225"
    assert abs(s["cost_price"] - 1.8361) < 1e-9
    assert s["stock"] == 100
