from dataclasses import dataclass

DEFAULT_OPERATING_RATE = 0.30  # 平台佣金+广告+优惠券+退货等，占售价比例（估算）


@dataclass
class ProfitEstimate:
    selling_price: float
    purchase_cost: float
    operating_cost: float
    profit: float
    margin: float
    confidence: str  # high / medium / low


def estimate_profit(selling_price, certain_cost,
                    operating_rate: float = DEFAULT_OPERATING_RATE,
                    estimated_purchase_cost=None):
    """计算利润估算。数据不足返回 None。

    certain_cost: ERP 真实落地成本（自家商品有）；为 None 时用 estimated_purchase_cost。
    """
    purchase = certain_cost if certain_cost is not None else estimated_purchase_cost
    if selling_price is None or selling_price <= 0 or purchase is None:
        return None
    operating = selling_price * operating_rate
    profit = selling_price - purchase - operating
    margin = profit / selling_price
    if certain_cost is None:
        confidence = "low"
    elif operating_rate <= 0.35:
        confidence = "high"
    else:
        confidence = "medium"
    return ProfitEstimate(
        selling_price=round(selling_price, 4),
        purchase_cost=round(purchase, 4),
        operating_cost=round(operating, 4),
        profit=round(profit, 4),
        margin=round(margin, 4),
        confidence=confidence,
    )
