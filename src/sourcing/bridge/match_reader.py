import sqlite3
from dataclasses import dataclass


@dataclass
class MatchRow:
    platform: str
    external_product_id: str
    erp_sku: str
    image_score: float | None
    title_score: float | None
    category_score: float | None
    price_score: float | None
    final_score: float | None
    match_status: str | None


_COLUMNS = ["platform", "external_product_id", "erp_sku", "image_score", "title_score",
            "category_score", "price_score", "final_score", "match_status"]


def read_match_results(app_db_path: str) -> list[MatchRow]:
    conn = sqlite3.connect(app_db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM match_results")
        rows = []
        for r in cur.fetchall():
            rows.append(MatchRow(
                platform=(r["platform"] or "").strip(),
                external_product_id=(r["external_product_id"] or "").strip(),
                erp_sku=(r["erp_sku"] or "").strip(),
                image_score=r["image_score"], title_score=r["title_score"],
                category_score=r["category_score"], price_score=r["price_score"],
                final_score=r["final_score"], match_status=r["match_status"],
            ))
        return rows
    finally:
        conn.close()
