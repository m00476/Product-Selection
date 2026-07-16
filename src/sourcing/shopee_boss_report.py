from __future__ import annotations

from sourcing import erp_image_search as e


KEEP_VERDICTS = {"高置信匹配", "可能匹配"}

SHOPEE_BOSS_REPORT_FIELDS = [
    "排名",
    "Shopee商品ID",
    "商品图片链接",
    "商品类目",
    "Shopee商品链接",
    "商品标题",
    "地区",
    "评分",
    "价格",
    "总销售件数",
    "30天总销售件数",
    "30天总销售金额",
    "收藏数",
    "评价数",
    "上架时间",
    "店铺名称",
    "店铺开张时间",
    "用户名称",
    "匹配判定",
    "嵌入相似度",
    "ERP以图搜索相似度",
    "ERP候选排名",
    "ERP子SKU",
    "ERP主SKU",
    "ERP商品状态",
    "ERP图片链接",
    "ERP库存",
    "ERP销量",
    "ERP子SKU数量",
    "建议动作",
]


def _value(row: dict, key: str) -> str:
    value = row.get(key, "")
    return "" if value in (None, "None") else str(value)


def _action(verdict: str, status: str) -> str:
    if verdict == "高置信匹配":
        if "正常" in status:
            return "高置信同款，ERP正常在售；通常不作为新品，优先评估跟卖/价格/库存策略"
        return "高置信同款，先确认ERP状态、库存和供应链；正常在售则不作为新品"
    if verdict == "可能匹配":
        return "可能同款，建议人工看图确认；确认同款后再看ERP库存、销量和供应链"
    return ""


def build_shopee_boss_report_rows(source_rows: list[dict], match_rows: list[dict]) -> list[dict]:
    """Preserve Shopee export fields and append the best actionable ERP match."""
    best_matches = e._best_match_by_external_sku(match_rows)
    report_rows = []
    for source in source_rows:
        sku = _value(source, "sku").strip()
        match = best_matches.get(sku, {})
        verdict = e.best_match_verdict(e._embedding_value(match)) if match else "未参与本次匹配"
        if verdict not in KEEP_VERDICTS:
            continue
        status = e._erp_status_text(match)
        report_rows.append(
            {
                "排名": _value(source, "source_rank"),
                "Shopee商品ID": sku,
                "商品图片链接": _value(source, "image_url"),
                "商品类目": _value(source, "category"),
                "Shopee商品链接": _value(source, "product_url"),
                "商品标题": _value(source, "product_name"),
                "地区": _value(source, "location"),
                "评分": _value(source, "rating"),
                "价格": _value(source, "price"),
                "总销售件数": _value(source, "sales"),
                "30天总销售件数": _value(source, "sales_30d"),
                "30天总销售金额": _value(source, "sales_revenue_30d"),
                "收藏数": _value(source, "favorites"),
                "评价数": _value(source, "review_count"),
                "上架时间": _value(source, "listed_at"),
                "店铺名称": _value(source, "seller_name"),
                "店铺开张时间": _value(source, "seller_opened_at"),
                "用户名称": _value(source, "seller_username"),
                "匹配判定": verdict,
                "嵌入相似度": _value(match, "embedding_similarity"),
                "ERP以图搜索相似度": _value(match, "similarity"),
                "ERP候选排名": _value(match, "match_rank"),
                "ERP子SKU": _value(match, "matched_erp_sku"),
                "ERP主SKU": _value(match, "matched_main_sku"),
                "ERP商品状态": status,
                "ERP图片链接": _value(match, "erp_image_url"),
                "ERP库存": _value(match, "erp_total_inventory"),
                "ERP销量": _value(match, "erp_sales_num"),
                "ERP子SKU数量": _value(match, "erp_subsku_count"),
                "建议动作": _action(verdict, status),
            }
        )
    return report_rows
