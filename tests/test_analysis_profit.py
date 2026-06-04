from sourcing.analysis.profit import estimate_profit, ProfitEstimate


def test_own_product_high_confidence():
    est = estimate_profit(selling_price=100.0, certain_cost=40.0, operating_rate=0.30)
    assert est.purchase_cost == 40.0
    assert est.operating_cost == 30.0
    assert est.profit == 30.0
    assert abs(est.margin - 0.30) < 1e-9
    assert est.confidence == "high"


def test_own_product_medium_confidence_when_operating_high():
    est = estimate_profit(selling_price=100.0, certain_cost=40.0, operating_rate=0.40)
    assert est.confidence == "medium"


def test_competitor_low_confidence_uses_estimated_purchase():
    est = estimate_profit(selling_price=100.0, certain_cost=None,
                          operating_rate=0.30, estimated_purchase_cost=40.0)
    assert est.purchase_cost == 40.0
    assert est.confidence == "low"


def test_insufficient_data_returns_none():
    assert estimate_profit(selling_price=None, certain_cost=10.0) is None
    assert estimate_profit(selling_price=0.0, certain_cost=10.0) is None
    assert estimate_profit(selling_price=100.0, certain_cost=None,
                           estimated_purchase_cost=None) is None
