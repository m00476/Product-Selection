from sourcing.analysis.scoring import score_opportunity, OpportunityScore


def test_zero_sales_gives_zero_score():
    s = score_opportunity(sales=0, margin=0.3, review_rating=5.0, review_count=100)
    assert s.score == 0.0


def test_negative_margin_zeroes_profit_component():
    s = score_opportunity(sales=1000, margin=-0.1, review_rating=4.5, review_count=50)
    assert s.profit_component == 0.0
    assert s.score == 0.0


def test_higher_sales_scores_higher():
    low = score_opportunity(sales=100, margin=0.3, review_rating=4.5, review_count=50)
    high = score_opportunity(sales=10000, margin=0.3, review_rating=4.5, review_count=50)
    assert high.score > low.score


def test_reason_mentions_margin_and_rating():
    s = score_opportunity(sales=2000, margin=0.35, review_rating=4.6, review_count=150)
    assert "35%" in s.reason
    assert "4.6" in s.reason


def test_handles_none_reviews():
    s = score_opportunity(sales=500, margin=0.2, review_rating=None, review_count=None)
    assert isinstance(s, OpportunityScore)
    assert s.review_component == 0.0
