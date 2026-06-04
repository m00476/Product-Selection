import psycopg
from sourcing.analysis.profit import estimate_profit, DEFAULT_OPERATING_RATE
from sourcing.analysis.scoring import score_opportunity
from sourcing.analysis.store import (
    fetch_product_metrics, upsert_profit_estimate, upsert_opportunity_score,
)

DEFAULT_ASSUMED_COGS_RATE = 0.40  # 竞品：假设我们自采进货成本占其售价比例


def _f(value):
    return float(value) if value is not None else None


def run_analysis(conn: psycopg.Connection, *,
                 operating_rate: float = DEFAULT_OPERATING_RATE,
                 assumed_cogs_rate: float = DEFAULT_ASSUMED_COGS_RATE) -> dict:
    profit_n = 0
    opp_n = 0
    for r in fetch_product_metrics(conn):
        price = _f(r["price"])
        is_own = r["is_own"]
        certain = _f(r["cost_price"]) if is_own else None
        est_purchase = (price * assumed_cogs_rate) if (not is_own and price) else None
        est = estimate_profit(price, certain, operating_rate, est_purchase)
        if est is not None:
            upsert_profit_estimate(conn, r["product_id"], est)
            profit_n += 1
        if not is_own:
            margin = est.margin if est is not None else None
            opp = score_opportunity(_f(r["sales"]), margin, _f(r["review_rating"]),
                                    int(r["review_count"]) if r["review_count"] is not None else None)
            upsert_opportunity_score(conn, r["product_id"], opp)
            opp_n += 1
    return {"profit_estimates": profit_n, "opportunity_scores": opp_n}
