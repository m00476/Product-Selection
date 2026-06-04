from sourcing.urls import normalize_product_url


def test_ozon_bare_id():
    assert normalize_product_url("https://www.ozon.ru/product/3637903008") == (
        "ozon", "3637903008", "https://www.ozon.ru/product/3637903008")


def test_ozon_with_slug():
    assert normalize_product_url("https://www.ozon.ru/product/asus-zenbook-3637903008/") == (
        "ozon", "3637903008", "https://www.ozon.ru/product/3637903008")


def test_aliexpress_with_query_and_m_prefix():
    assert normalize_product_url("https://m.aliexpress.com/item/1005006.html?spm=a2g0o") == (
        "aliexpress", "1005006", "https://www.aliexpress.com/item/1005006.html")


def test_unknown_host():
    assert normalize_product_url("https://example.com/x") == ("unknown", None, None)


def test_empty():
    assert normalize_product_url("") == ("unknown", None, None)
    assert normalize_product_url(None) == ("unknown", None, None)


def test_aliexpress_no_item_id():
    assert normalize_product_url("https://www.aliexpress.com/store/123") == (
        "aliexpress", None, None)
