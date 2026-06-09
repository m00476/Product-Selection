"""一条龙：单品类 采集 → 两层图片匹配 → 报告。

为 Windows 计划任务设计：
- 采集失败 -> 立刻返回 failed，不往下跑（避免拿错/空数据出报告）
- 类目/headless 通过 env 传给采集子进程
- 每阶段 emit 一行日志（CLI 包一层写文件+stdout，并据 status 设退出码）
"""
import os

from sourcing.collect.orchestrator import collect_target
from sourcing.erp_image_pipeline import run_pipeline


def run_product(conn, *, source: str, product_type: str, base_dir: str,
                category: str | None = None, headless: bool | None = None,
                limit=None, threshold: float = 0.85,
                env=None, collect=collect_target, pipeline=run_pipeline,
                emit=print) -> dict:
    env = os.environ if env is None else env
    if category is not None:
        env["ALIEXPRESS_CATEGORY_NAME"] = category
    if headless is not None:
        env["SCRAPER_HEADLESS"] = "1" if headless else "0"

    emit(f"[run-product] collect start: source={source} product_type={product_type} "
         f"category={category or env.get('ALIEXPRESS_CATEGORY_NAME', '')!r}")
    collect_result = collect(conn, source, product_type, base_dir=base_dir)
    if collect_result.get("status") != "success":
        emit(f"[run-product] collect FAILED: {collect_result}")
        return {"status": "failed", "stage": "collect", "collect": collect_result}
    emit(f"[run-product] collect ok: {collect_result}")

    emit("[run-product] pipeline start: 图搜粗筛 + 嵌入精配 + 落库 + 报告")
    pipeline_result = pipeline(conn, source=source, product_type=product_type,
                               base_dir=base_dir, limit=limit, threshold=threshold)
    emit(f"[run-product] pipeline ok: {pipeline_result}")
    return {"status": "success", "stage": "done",
            "collect": collect_result, "pipeline": pipeline_result}
