# 利润估算与机会打分（Profit & Scoring）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在数据底座之上，计算每个商品的利润估算（确定/估算成本 + 置信等级），并对竞品（自家没有的）算选品机会分，结果写入 `profit_estimates` / `opportunity_scores` 供看板使用。

**Architecture:** 纯函数计算层（profit、scoring，无 DB、易测）+ 存储层（读最新快照、写分析表）+ 编排（runner + CLI 子命令）。规则加权、可解释，不上机器学习。

**Tech Stack:** Python 3.12、psycopg 3、pytest、PostgreSQL 16（已就绪，localhost:5432）。

参考设计：`docs/superpowers/specs/2026-06-04-product-sourcing-system-design.md` §6。依赖 Plan 1（已合并 master）的表：`products`、`price_snapshots`、`sales_snapshots`、`erp_skus`。

## 关键建模决定（来自设计与 ERP 实际字段）
- **确定成本**：ERP 的 `cost_price` 已是落地成本（实测 `成本价 = 加权采购价 + 加权运费 + 加权分拣费`），直接用，不再叠加分项。
- **运营成本**：平台佣金+广告+优惠券+退货等，MVP 统一按售价的固定比例 `operating_rate`（默认 0.30）估算，可配置。
- **竞品采购成本**：我们不知道竞品成本，按售价的 `assumed_cogs_rate`（默认 0.40）估算我们若自采的进货成本，**置信=low**，理由里写明假设。
- **置信等级**：`high`=有 ERP 真实成本且运营估算比例不高(<=0.35)；`medium`=有真实成本但运营比例较高(>0.35)；`low`=无真实成本（竞品，进货成本靠估算）。
- **竞争惩罚**：数据不足，MVP 不计（设计中属二期），机会分不含该项。
- 利润对**所有有售价的商品**算；机会分只对**竞品**（`is_own=false`）算。

## File Structure
```
migrations/003_analysis.sql                 # profit_estimates + opportunity_scores
src/sourcing/analysis/__init__.py
src/sourcing/analysis/profit.py             # estimate_profit() 纯函数
src/sourcing/analysis/scoring.py            # score_opportunity() 纯函数
src/sourcing/analysis/store.py              # 读最新快照指标 + upsert 写分析表
src/sourcing/analysis/run.py                # run_analysis() 编排
tests/test_analysis_profit.py
tests/test_analysis_scoring.py
tests/test_analysis_store.py
tests/test_analysis_run.py
src/sourcing/cli.py                         # 增加 analyze 子命令（修改）
```

---

## Task 1: 迁移 003 — 分析结果表

**Files:** Create `migrations/003_analysis.sql`; Test `tests/test_analysis_store.py` (structure check appended later — here add a dedicated migration test).

- [ ] **Step 1: 写失败测试 `tests/test_analysis_store.py`**

```python
def test_analysis_tables_exist(conn):
    with conn.cursor() as cur:
        for table in ["profit_estimates", "opportunity_scores"]:
            cur.execute("SELECT to_regclass(%s)", (table,))
            assert cur.fetchone()[0] is not None, table


def test_profit_estimates_unique_product(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, is_own) VALUES ('ozon', false) RETURNING product_id")
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO profit_estimates (product_id, confidence) VALUES (%s, 'low')", (pid,))
        cur.execute(
            "INSERT INTO profit_estimates (product_id, confidence) VALUES (%s, 'high') "
            "ON CONFLICT (product_id) DO UPDATE SET confidence = EXCLUDED.confidence", (pid,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (pid,))
        assert cur.fetchone()[0] == "high"
        cur.execute("SELECT count(*) FROM profit_estimates")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行 `pytest tests/test_analysis_store.py -v`，确认 FAIL（表不存在）。**

- [ ] **Step 3: 创建 `migrations/003_analysis.sql`**

```sql
CREATE TABLE profit_estimates (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id     BIGINT REFERENCES products(product_id),
    selling_price  NUMERIC,
    purchase_cost  NUMERIC,
    operating_cost NUMERIC,
    profit         NUMERIC,
    margin         NUMERIC,
    confidence     TEXT,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_profit UNIQUE (product_id)
);

CREATE TABLE opportunity_scores (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id       BIGINT REFERENCES products(product_id),
    score            NUMERIC,
    sales_component  NUMERIC,
    profit_component NUMERIC,
    review_component NUMERIC,
    reason           TEXT,
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_opportunity UNIQUE (product_id)
);
```

- [ ] **Step 4: 运行 `pytest tests/test_analysis_store.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add migrations/003_analysis.sql tests/test_analysis_store.py
git commit -m "feat: migration 003 profit_estimates + opportunity_scores"
```

---

## Task 2: 利润估算纯函数

**Files:** Create `src/sourcing/analysis/__init__.py` (empty), `src/sourcing/analysis/profit.py`; Test `tests/test_analysis_profit.py`.

- [ ] **Step 1: 写失败测试 `tests/test_analysis_profit.py`**

```python
from sourcing.analysis.profit import estimate_profit, ProfitEstimate


def test_own_product_high_confidence():
    # 售价100，确定成本40，运营30% -> 利润=100-40-30=30，毛利率0.3
    est = estimate_profit(selling_price=100.0, certain_cost=40.0, operating_rate=0.30)
    assert est.purchase_cost == 40.0
    assert est.operating_cost == 30.0
    assert est.profit == 30.0
    assert abs(est.margin - 0.30) < 1e-9
    assert est.confidence == "high"


def test_own_product_medium_confidence_when_operating_high():
    est = estimate_profit(selling_price=100.0, certain_cost=40.0, operating_rate=0.40)
    assert est.confidence == "medium"


def test_competitor_low_confidence_uses_estimated_purchase():
    est = estimate_profit(selling_price=100.0, certain_cost=None,
                          operating_rate=0.30, estimated_purchase_cost=40.0)
    assert est.purchase_cost == 40.0
    assert est.confidence == "low"


def test_insufficient_data_returns_none():
    assert estimate_profit(selling_price=None, certain_cost=10.0) is None
    assert estimate_profit(selling_price=0.0, certain_cost=10.0) is None
    assert estimate_profit(selling_price=100.0, certain_cost=None,
                           estimated_purchase_cost=None) is None
```

- [ ] **Step 2: 运行 `pytest tests/test_analysis_profit.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/analysis/__init__.py`（空）与 `src/sourcing/analysis/profit.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_analysis_profit.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/analysis/__init__.py src/sourcing/analysis/profit.py tests/test_analysis_profit.py
git commit -m "feat: profit estimation pure function with confidence levels"
```

---

## Task 3: 机会打分纯函数

**Files:** Create `src/sourcing/analysis/scoring.py`; Test `tests/test_analysis_scoring.py`.

- [ ] **Step 1: 写失败测试 `tests/test_analysis_scoring.py`**

```python
from sourcing.analysis.scoring import score_opportunity, OpportunityScore


def test_zero_sales_gives_zero_score():
    s = score_opportunity(sales=0, margin=0.3, review_rating=5.0, review_count=100)
    assert s.score == 0.0


def test_negative_margin_zeroes_profit_component():
    s = score_opportunity(sales=1000, margin=-0.1, review_rating=4.5, review_count=50)
    assert s.profit_component == 0.0
    assert s.score == 0.0


def test_higher_sales_scores_higher():
    low = score_opportunity(sales=100, margin=0.3, review_rating=4.5, review_count=50)
    high = score_opportunity(sales=10000, margin=0.3, review_rating=4.5, review_count=50)
    assert high.score > low.score


def test_reason_mentions_margin_and_rating():
    s = score_opportunity(sales=2000, margin=0.35, review_rating=4.6, review_count=150)
    assert "35%" in s.reason
    assert "4.6" in s.reason


def test_handles_none_reviews():
    s = score_opportunity(sales=500, margin=0.2, review_rating=None, review_count=None)
    assert isinstance(s, OpportunityScore)
    assert s.review_component == 0.0
```

- [ ] **Step 2: 运行 `pytest tests/test_analysis_scoring.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/analysis/scoring.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_analysis_scoring.py -v`，确认 PASS。**

> 说明：`test_reason_mentions_margin_and_rating` 依赖 `f"{0.35:.0%}"=="35%"` 与评分原值 `4.6` 出现在理由串。

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/analysis/scoring.py tests/test_analysis_scoring.py
git commit -m "feat: rule-based opportunity scoring pure function"
```

---

## Task 4: 存储层 — 读最新指标 + 写分析表

**Files:** Modify `src/sourcing/analysis/store.py` (create); Test: append to `tests/test_analysis_store.py`.

- [ ] **Step 1: APPEND 失败测试到 `tests/test_analysis_store.py`**

```python
from datetime import datetime, timezone
from sourcing.analysis.store import (
    fetch_product_metrics, upsert_profit_estimate, upsert_opportunity_score,
)
from sourcing.analysis.profit import estimate_profit
from sourcing.analysis.scoring import score_opportunity


def _seed_competitor(conn):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon', '500', false) RETURNING product_id")
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, "
                    "price, observed_at) VALUES (%s,'seerfar','ozon','500',100.0,%s)", (pid, now))
        cur.execute("INSERT INTO sales_snapshots (product_id, source, platform, platform_product_id, "
                    "sales, review_count, review_rating, observed_at) "
                    "VALUES (%s,'seerfar','ozon','500',2000,150,4.6,%s)", (pid, now))
    conn.commit()
    return pid


def test_fetch_product_metrics_returns_latest(conn):
    pid = _seed_competitor(conn)
    rows = fetch_product_metrics(conn)
    row = [r for r in rows if r["product_id"] == pid][0]
    assert row["is_own"] is False
    assert float(row["price"]) == 100.0
    assert float(row["sales"]) == 2000
    assert row["cost_price"] is None


def test_upsert_profit_and_opportunity(conn):
    pid = _seed_competitor(conn)
    est = estimate_profit(100.0, None, 0.30, estimated_purchase_cost=40.0)
    upsert_profit_estimate(conn, pid, est)
    upsert_profit_estimate(conn, pid, est)  # 幂等
    opp = score_opportunity(2000, est.margin, 4.6, 150)
    upsert_opportunity_score(conn, pid, opp)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM profit_estimates")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (pid,))
        assert cur.fetchone()[0] == "low"
        cur.execute("SELECT count(*) FROM opportunity_scores WHERE product_id=%s", (pid,))
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行 `pytest tests/test_analysis_store.py -v`，确认新测试 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/analysis/store.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_analysis_store.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/analysis/store.py tests/test_analysis_store.py
git commit -m "feat: analysis store - latest metrics read + upsert writers"
```

---

## Task 5: 编排 runner + CLI analyze 子命令

**Files:** Create `src/sourcing/analysis/run.py`; Modify `src/sourcing/cli.py`; Test `tests/test_analysis_run.py`.

- [ ] **Step 1: 写失败测试 `tests/test_analysis_run.py`**

```python
from datetime import datetime, timezone
from sourcing.analysis.run import run_analysis


def _seed(conn):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        # 竞品：有售价+销量，无 ERP 成本
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon','500',false) RETURNING product_id")
        comp = cur.fetchone()[0]
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'seerfar','ozon','500',100.0,%s)", (comp, now))
        cur.execute("INSERT INTO sales_snapshots (product_id, source, platform, platform_product_id, sales, review_count, review_rating, observed_at) "
                    "VALUES (%s,'seerfar','ozon','500',2000,150,4.6,%s)", (comp, now))
        # 自家：有 ERP 成本 + 售价
        cur.execute("INSERT INTO products (platform, is_own) VALUES ('erp', true) RETURNING product_id")
        own = cur.fetchone()[0]
        cur.execute("INSERT INTO erp_skus (sku, own_product_id, cost_price) VALUES ('SKU1',%s,40.0)", (own,))
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'erp','erp',NULL,90.0,%s)", (own, now))
    conn.commit()
    return comp, own


def test_run_analysis_computes_both(conn):
    comp, own = _seed(conn)
    summary = run_analysis(conn)
    # 两个商品都有售价 -> 两条利润估算；只有竞品算机会分
    assert summary["profit_estimates"] == 2
    assert summary["opportunity_scores"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (own,))
        assert cur.fetchone()[0] == "high"   # 有真实成本
        cur.execute("SELECT confidence FROM profit_estimates WHERE product_id=%s", (comp,))
        assert cur.fetchone()[0] == "low"    # 竞品估算成本
        cur.execute("SELECT score FROM opportunity_scores WHERE product_id=%s", (comp,))
        assert float(cur.fetchone()[0]) > 0
```

- [ ] **Step 2: 运行 `pytest tests/test_analysis_run.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/analysis/run.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_analysis_run.py -v`，确认 PASS。**

- [ ] **Step 5: 修改 `src/sourcing/cli.py` 增加 `analyze` 子命令。** 用 argparse 子命令替换原单一逻辑。完整新内容：

```python
import argparse
from sourcing import config, db
from sourcing.importer import import_seerfar_csv
from sourcing.analysis.run import run_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Sourcing pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="导入源 CSV 到 PostgreSQL")
    imp.add_argument("--source", required=True, choices=["seerfar"])
    imp.add_argument("--path", required=True, help="CSV 文件路径")
    imp.add_argument("--product-type", required=True)

    sub.add_parser("analyze", help="计算利润估算与机会分")

    args = parser.parse_args()
    conn = db.connect(config.database_url())
    try:
        if args.command == "import":
            summary = import_seerfar_csv(
                conn, args.path, product_type=args.product_type, source_file=args.path)
            print(f"[DONE] imported: {summary}")
        elif args.command == "analyze":
            summary = run_analysis(conn)
            print(f"[DONE] analyzed: {summary}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

> 注意：这是破坏性 CLI 变更（旧 `--source/--path` 现在在 `import` 子命令下）。README 的导入示例需相应更新为 `python -m sourcing.cli import --source seerfar ...`（在 Task 6 处理）。

- [ ] **Step 6: 验证 CLI 可导入：`python -c "import sourcing.cli; print('cli ok')"`，期望打印 `cli ok`。**

- [ ] **Step 7: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 8: Commit**
```
git add src/sourcing/analysis/run.py src/sourcing/cli.py tests/test_analysis_run.py
git commit -m "feat: analysis runner + cli analyze subcommand"
```

---

## Task 6: 更新 README 导入命令

**Files:** Modify `README.md`.

- [ ] **Step 1: 把 README「导入数据」一节替换为子命令用法**

将原：
```
python -m sourcing.cli --source seerfar --path <CSV路径> --product-type <品类>
```
替换为：
````markdown
## 导入数据
```powershell
python -m sourcing.cli import --source seerfar --path <CSV路径> --product-type <品类>
```

## 计算利润与机会分
```powershell
python -m sourcing.cli analyze
```
结果写入 `profit_estimates`、`opportunity_scores` 两张表。
````

- [ ] **Step 2: Commit**
```
git add README.md
git commit -m "docs: update CLI usage for import/analyze subcommands"
```

---

## Self-Review 结论
- **Spec 覆盖**：§6 利润估算（确定/估算成本+置信 high/medium/low）→ Task 2；机会打分（销量×利润×评价−竞争）→ Task 3（竞争项按设计 MVP 不计，已注明）；结果表 → Task 1；落库与编排 → Task 4/5。
- **占位符**：无 TODO/TBD；所有代码步骤含完整可执行代码。
- **类型一致性**：`ProfitEstimate`/`OpportunityScore` 字段在 profit/scoring、store、run、测试间一致；`estimate_profit`、`score_opportunity`、`fetch_product_metrics`、`upsert_profit_estimate`、`upsert_opportunity_score`、`run_analysis` 签名跨任务一致。
- **已知简化（YAGNI）**：竞争惩罚不计；竞品采购成本用固定 `assumed_cogs_rate` 估算（low 置信）；运营成本用固定 `operating_rate`；这些常量后续可改为配置/按类目细化（留待后续）。
- **依赖**：Plan 1 已合并 master，表均存在；不修改 Plan 1 代码，仅新增 analysis 包并扩展 CLI。
