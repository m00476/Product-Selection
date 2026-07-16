import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from sourcing import erp_image_search as e


KEEP_VERDICTS = {"高置信匹配", "可能匹配"}
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()

    input_rows = e._read_csv_dicts(args.input_csv)
    match_rows = e._read_csv_dicts(e.output_csv_path(args.base_dir, "seerfar", args.product_type))
    best = e._best_match_by_external_sku(match_rows)

    rows = []
    for source in input_rows:
        sku = _value(source, "sku").strip()
        match = best.get(sku, {})
        verdict = e.best_match_verdict(e._embedding_value(match)) if match else "未参与本次匹配"
        if verdict not in KEEP_VERDICTS:
            continue
        status = e._erp_status_text(match)
        rows.append(
            {
                "排名": _value(source, "source_rank"),
                "TikTok商品ID": sku,
                "商品名称": _value(source, "product_name"),
                "商品状态": _value(source, "sale_mode"),
                "店铺名称": _value(source, "seller_name"),
                "国家/地区": _value(source, "country_region"),
                "商品分类": _value(source, "category"),
                "售价": _value(source, "price"),
                "佣金比例": _value(source, "commission_rate"),
                "7天销量": _value(source, "sales_7d"),
                "总销量": _value(source, "sales"),
                "总销售额": _value(source, "sales_revenue"),
                "带货达人总数": _value(source, "creator_count"),
                "达人出单率": _value(source, "creator_order_rate"),
                "带货视频总数": _value(source, "video_count"),
                "带货直播总数": _value(source, "live_count"),
                "预估商品上架时间": _value(source, "listed_at"),
                "商品图片链接": _value(source, "image_url"),
                "本地图片路径": _value(source, "local_image_path"),
                "TikTok商品落地页": _value(source, "product_url"),
                "FastMoss商品详情页": _value(source, "fastmoss_product_url"),
                "FastMoss店铺详情页": _value(source, "fastmoss_shop_url"),
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

    output_dir = Path(args.base_dir) / "output" / "image_search" / "tiktok" / args.product_type
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / "tiktok_boss_report.csv"
    xlsx_path = output_dir / f"TikTok_FastMoss_老板版报告_{timestamp}.xlsx"
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    print(
        {
            "rows": len(rows),
            "verdicts": df["匹配判定"].value_counts().to_dict() if not df.empty else {},
            "csv": str(csv_path),
            "xlsx": str(xlsx_path),
        }
    )


if __name__ == "__main__":
    main()
