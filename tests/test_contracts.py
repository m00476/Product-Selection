from datetime import datetime, timezone
from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot


def test_normalized_product_defaults():
    p = NormalizedProduct(
        source="seerfar", platform="ozon", platform_product_id="3637903008",
        canonical_url="https://www.ozon.ru/product/3637903008",
        source_record_id="3637903008", product_type="laptop",
    )
    assert p.is_own is False
    assert p.title is None


def test_snapshots_require_observed_at():
    now = datetime.now(timezone.utc)
    ps = PriceSnapshot(source="seerfar", platform="ozon", platform_product_id="1",
                       price=91510.0, currency="RUB", observed_at=now,
                       collected_at=now, metric_source="seerfar")
    ss = SalesSnapshot(source="seerfar", platform="ozon", platform_product_id="1",
                       sales=553, review_count=28, review_rating=5.0,
                       observed_at=now, collected_at=now, metric_source="seerfar")
    assert ps.price == 91510.0 and ss.sales == 553
