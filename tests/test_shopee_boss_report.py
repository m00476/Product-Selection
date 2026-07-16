from sourcing.shopee_boss_report import build_shopee_boss_report_rows


def test_shopee_boss_report_keeps_actionable_matches_and_source_fields():
    source_rows = [
        {
            "source_rank": "1",
            "sku": "SH-1",
            "product_name": "Floor mat",
            "image_url": "https://image.example/sh-1.jpg",
            "product_url": "https://shopee.example/sh-1",
            "category": "Home",
            "price": "19.9",
            "sales": "1000",
            "sales_30d": "200",
            "sales_revenue_30d": "3990",
            "favorites": "50",
            "review_count": "40",
            "seller_name": "Shop A",
        },
        {"source_rank": "2", "sku": "SH-2", "product_name": "Weak item"},
    ]
    match_rows = [
        {
            "external_sku": "SH-1",
            "matched_erp_sku": "ERP-1",
            "matched_main_sku": "MAIN-1",
            "erp_product_status": "8",
            "erp_total_inventory": "7",
            "erp_sales_num": "3",
            "embedding_similarity": "0.91",
            "similarity": "0.8",
            "match_rank": "1",
        },
        {"external_sku": "SH-2", "embedding_similarity": "0.6"},
    ]

    rows = build_shopee_boss_report_rows(source_rows, match_rows)

    assert len(rows) == 1
    assert rows[0]["Shopee商品ID"] == "SH-1"
    assert rows[0]["30天总销售件数"] == "200"
    assert rows[0]["商品图片链接"] == "https://image.example/sh-1.jpg"
    assert rows[0]["ERP子SKU"] == "ERP-1"
    assert rows[0]["匹配判定"] == "高置信匹配"
