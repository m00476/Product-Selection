import psycopg
from sourcing.analysis.profit import ProfitEstimate
from sourcing.analysis.scoring import OpportunityScore

_METRICS_SQL = """
SELECT p.product_id, p.is_own,
       lp.price, ls.sales, ls.review_rating, ls.review_count,
       e.cost_price
FROM products p
LEFT JOIN LATERAL (
    SELECT price FROM price_snapshots ps
    WHERE ps.product_id = p.product_id
    ORDER BY collected_at DESC, observed_at DESC LIMIT 1
) lp ON true
LEFT JOIN LATERAL (
    SELECT sales, review_rating, review_count FROM sales_snapshots ss
    WHERE ss.product_id = p.product_id
    ORDER BY collected_at DESC, observed_at DESC LIMIT 1
) ls ON true
LEFT JOIN erp_skus e ON e.own_product_id = p.product_id
"""


def fetch_product_metrics(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(_METRICS_SQL)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def upsert_profit_estimate(conn: psycopg.Connection, product_id: int, est: ProfitEstimate) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO profit_estimates
                (product_id, selling_price, purchase_cost, operating_cost, profit, margin, confidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_id) DO UPDATE SET
                selling_price=EXCLUDED.selling_price, purchase_cost=EXCLUDED.purchase_cost,
                operating_cost=EXCLUDED.operating_cost, profit=EXCLUDED.profit,
                margin=EXCLUDED.margin, confidence=EXCLUDED.confidence, computed_at=now()
            """,
            (product_id, est.selling_price, est.purchase_cost, est.operating_cost,
             est.profit, est.margin, est.confidence),
        )
    conn.commit()


def upsert_opportunity_score(conn: psycopg.Connection, product_id: int, opp: OpportunityScore) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO opportunity_scores
                (product_id, score, sales_component, profit_component, review_component, reason)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_id) DO UPDATE SET
                score=EXCLUDED.score, sales_component=EXCLUDED.sales_component,
                profit_component=EXCLUDED.profit_component, review_component=EXCLUDED.review_component,
                reason=EXCLUDED.reason, computed_at=now()
            """,
            (product_id, opp.score, opp.sales_component, opp.profit_component,
             opp.review_component, opp.reason),
        )
    conn.commit()
