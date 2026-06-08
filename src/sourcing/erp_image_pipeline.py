"""一键编排：外部平台数据 -> 两层匹配(ERP图搜粗筛 + DINOv2嵌入精配) -> 落库 + 报告。"""
import psycopg

from sourcing.erp_image_search import run_image_search, generate_boss_decision_report
from sourcing.rerank.embed import rerank_image_search
from sourcing.bridge.image_decisions import load_image_decisions


def run_pipeline(conn: psycopg.Connection, *, source: str, product_type: str,
                 base_dir: str, limit=None, threshold: float = 0.85,
                 delay_seconds: float = 0.5) -> dict:
    """依次：① ERP以图搜款(粗筛) ② DINOv2嵌入复核(精配) ③ 落库 ④ 出决策报告。
    只需事先准备好 input/<市场>/<品类>/*.csv（外部平台数据，含 image_url）。"""
    search = run_image_search(source=source, product_type=product_type,
                              base_dir=base_dir, limit=limit, delay_seconds=delay_seconds)
    rerank = rerank_image_search(source=source, product_type=product_type,
                                 base_dir=base_dir, threshold=threshold)
    load = load_image_decisions(conn, source=source, product_type=product_type, base_dir=base_dir)
    report = generate_boss_decision_report(source=source, product_type=product_type, base_dir=base_dir)
    return {"search": search, "rerank": rerank, "load": load, "report": report}
