import math
from dataclasses import dataclass


@dataclass
class OpportunityScore:
    score: float
    sales_component: float
    profit_component: float
    review_component: float
    reason: str


def score_opportunity(sales, margin, review_rating, review_count) -> OpportunityScore:
    """规则加权机会分（可解释，无机器学习）。

    score = 销量热度 × 利润空间 × (1 + 评价质量)
    - 销量热度：log10(sales+1)
    - 利润空间：max(0, margin)（负毛利记 0）
    - 评价质量：(rating/5) × log10(review_count+1)
    竞争惩罚数据不足，MVP 不计。
    """
    sales_h = math.log10(sales + 1) if sales and sales > 0 else 0.0
    profit_c = max(0.0, margin) if margin is not None else 0.0
    rating_n = (review_rating or 0) / 5.0
    review_c = rating_n * math.log10((review_count or 0) + 1)
    score = sales_h * profit_c * (1 + review_c)
    reason = (
        f"销量热度{sales_h:.2f}×毛利率{profit_c:.0%}，"
        f"评分{review_rating if review_rating is not None else 0}/5"
        f"（{review_count or 0}条评论）"
    )
    return OpportunityScore(
        score=round(score, 4),
        sales_component=round(sales_h, 4),
        profit_component=round(profit_c, 4),
        review_component=round(review_c, 4),
        reason=reason,
    )
