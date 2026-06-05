# ERP 图搜决策落库 + 看板（Plan 4C）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 ERP 以图搜款的"老板决策"结果从 CSV/MD 落进 PostgreSQL，加一个去重好的视图，让它接进现有 Metabase 看板（和 v_opportunities 同款套路）。

**Architecture:** 复用 `erp_image_search.py` 已有的 `build_boss_decision_rows`（把图搜结果 CSV 归纳成一商品一决策）。新增：表 `erp_image_decisions` + 视图 `v_erp_image_decisions` + 落库函数 `bridge/image_decisions.py` + CLI `erp-image-load-db`。展示层在 Metabase 加卡片。

**Tech Stack:** PostgreSQL、psycopg、pytest、Metabase。

依赖已合并：`erp_image_search.py`（`build_boss_decision_rows`、`output_csv_path`、`_read_csv_dicts`、`BOSS_DECISION_FIELDS`）；migrations 001-005。

## 关键事实
- 决策行字段（= `BOSS_DECISION_FIELDS`）：source, product_type, external_sku, external_product_name, external_product_url, external_image_url, final_decision, boss_action, candidate_count, normal_candidate_count, stopped_candidate_count, limited_candidate_count, risk_candidate_count, top_erp_skus, top_main_skus。
- ERP 图搜响应**不含相似度**，决策依据是 ERP 商品状态（正常/停产/采购受限/风险）+ 候选数。视图不依赖 similarity。
- 图搜输出在 `<COLLECT_518_DIR>/output/image_search/<source>/<product_type>/`，故落库要用 `base_dir=config.collect_base_dir()`（一并消除之前 decision-report base_dir 默认不一致的坑）。

## File Structure
```
migrations/006_image_decisions.sql        # erp_image_decisions 表 + v_erp_image_decisions 视图
src/sourcing/bridge/image_decisions.py     # 读决策 CSV -> 归纳 -> upsert 入库
src/sourcing/cli.py                        # 增加 erp-image-load-db 子命令（修改）
tests/test_image_decisions.py
tests/test_cli.py                          # 追加 erp-image-load-db 用例（修改）
```

---

## Task 1: 迁移 006 — 决策表 + 视图

**Files:** Create `migrations/006_image_decisions.sql`; Test `tests/test_image_decisions.py`.

- [ ] **Step 1: 写失败测试 `tests/test_image_decisions.py`**

```python
def test_image_decisions_table_and_view_exist(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('erp_image_decisions')")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regclass('v_erp_image_decisions')")
        assert cur.fetchone()[0] is not None


def test_image_decisions_unique_and_view_flag(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO erp_image_decisions (source, product_type, external_sku, final_decision) "
            "VALUES ('ixspy','bags','S1','疑似新品机会')")
        cur.execute(
            "INSERT INTO erp_image_decisions (source, product_type, external_sku, final_decision) "
            "VALUES ('ixspy','bags','S1','疑似已有正常同款') "
            "ON CONFLICT (source, product_type, external_sku) DO UPDATE SET "
            "final_decision=EXCLUDED.final_decision")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM erp_image_decisions")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT final_decision, is_new_opportunity FROM v_erp_image_decisions WHERE external_sku='S1'")
        decision, is_opp = cur.fetchone()
        assert decision == "疑似已有正常同款"
        assert is_opp is False
```

- [ ] **Step 2: 运行 `pytest tests/test_image_decisions.py -v`，确认 FAIL。**

- [ ] **Step 3: 创建 `migrations/006_image_decisions.sql`**

```sql
CREATE TABLE erp_image_decisions (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source                  TEXT NOT NULL,
    product_type            TEXT NOT NULL,
    external_sku            TEXT NOT NULL,
    external_product_name   TEXT,
    external_product_url    TEXT,
    external_image_url      TEXT,
    final_decision          TEXT,
    boss_action             TEXT,
    candidate_count         INTEGER,
    normal_candidate_count  INTEGER,
    stopped_candidate_count INTEGER,
    limited_candidate_count INTEGER,
    risk_candidate_count    INTEGER,
    top_erp_skus            TEXT,
    top_main_skus           TEXT,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_image_decision UNIQUE (source, product_type, external_sku)
);

CREATE VIEW v_erp_image_decisions AS
SELECT
    source,
    product_type,
    external_sku,
    external_product_name,
    external_product_url,
    external_image_url,
    final_decision,
    boss_action,
    candidate_count,
    normal_candidate_count,
    stopped_candidate_count,
    risk_candidate_count,
    top_erp_skus,
    top_main_skus,
    (final_decision = '疑似新品机会') AS is_new_opportunity,
    generated_at
FROM erp_image_decisions;
```

- [ ] **Step 4: 运行 `pytest tests/test_image_decisions.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add migrations/006_image_decisions.sql tests/test_image_decisions.py
git commit -m "feat: migration 006 erp_image_decisions + view"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 2: 落库函数 image_decisions.py

**Files:** Create `src/sourcing/bridge/image_decisions.py`; Test: append to `tests/test_image_decisions.py`.

- [ ] **Step 1: APPEND 失败测试到 `tests/test_image_decisions.py`**（用临时图搜结果 CSV 喂）

```python
import csv
from pathlib import Path
from sourcing.bridge.image_decisions import load_image_decisions
from sourcing.erp_image_search import output_csv_path, RESULT_FIELDS


def _write_results_csv(base_dir, source, product_type, rows):
    path = output_csv_path(base_dir, source, product_type)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})


def test_load_image_decisions(conn, tmp_path):
    base = str(tmp_path)
    # 一个竞品两条候选：都正常 -> 决策"疑似已有正常同款"
    rows = [
        {"source": "ixspy", "product_type": "bags", "external_sku": "E1",
         "external_product_name": "Bag A", "matched_erp_sku": "ERP1",
         "match_status": "success", "erp_product_status": "8",
         "candidate_priority": "可用正常商品"},
        {"source": "ixspy", "product_type": "bags", "external_sku": "E1",
         "external_product_name": "Bag A", "matched_erp_sku": "ERP2",
         "match_status": "success", "erp_product_status": "8",
         "candidate_priority": "可用正常商品"},
        {"source": "ixspy", "product_type": "bags", "external_sku": "E2",
         "external_product_name": "Bag B", "matched_erp_sku": "",
         "match_status": "empty", "erp_product_status": "",
         "candidate_priority": "需人工确认"},
    ]
    _write_results_csv(base, "ixspy", "bags", rows)
    summary = load_image_decisions(conn, source="ixspy", product_type="bags", base_dir=base)
    assert summary["loaded"] == 2  # 两个竞品 E1,E2
    with conn.cursor() as cur:
        cur.execute("SELECT final_decision, normal_candidate_count FROM erp_image_decisions WHERE external_sku='E1'")
        assert cur.fetchone() == ("疑似已有正常同款", 2)
        cur.execute("SELECT is_new_opportunity FROM v_erp_image_decisions WHERE external_sku='E2'")
        assert cur.fetchone()[0] is True  # E2 无候选 -> 新品机会
    # 幂等：再跑一次不重复
    load_image_decisions(conn, source="ixspy", product_type="bags", base_dir=base)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM erp_image_decisions")
        assert cur.fetchone()[0] == 2
```

- [ ] **Step 2: 运行 `pytest tests/test_image_decisions.py -v`，确认新测试 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/bridge/image_decisions.py`**

```python
import psycopg

from sourcing.erp_image_search import (
    output_csv_path, _read_csv_dicts, build_boss_decision_rows,
)


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert_image_decision(conn: psycopg.Connection, d: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO erp_image_decisions
                (source, product_type, external_sku, external_product_name,
                 external_product_url, external_image_url, final_decision, boss_action,
                 candidate_count, normal_candidate_count, stopped_candidate_count,
                 limited_candidate_count, risk_candidate_count, top_erp_skus, top_main_skus)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, product_type, external_sku) DO UPDATE SET
                external_product_name=EXCLUDED.external_product_name,
                external_product_url=EXCLUDED.external_product_url,
                external_image_url=EXCLUDED.external_image_url,
                final_decision=EXCLUDED.final_decision, boss_action=EXCLUDED.boss_action,
                candidate_count=EXCLUDED.candidate_count,
                normal_candidate_count=EXCLUDED.normal_candidate_count,
                stopped_candidate_count=EXCLUDED.stopped_candidate_count,
                limited_candidate_count=EXCLUDED.limited_candidate_count,
                risk_candidate_count=EXCLUDED.risk_candidate_count,
                top_erp_skus=EXCLUDED.top_erp_skus, top_main_skus=EXCLUDED.top_main_skus,
                generated_at=now()
            """,
            (
                d.get("source"), d.get("product_type"), d.get("external_sku"),
                d.get("external_product_name"), d.get("external_product_url"),
                d.get("external_image_url"), d.get("final_decision"), d.get("boss_action"),
                _to_int(d.get("candidate_count")), _to_int(d.get("normal_candidate_count")),
                _to_int(d.get("stopped_candidate_count")), _to_int(d.get("limited_candidate_count")),
                _to_int(d.get("risk_candidate_count")), d.get("top_erp_skus"), d.get("top_main_skus"),
            ),
        )
    conn.commit()


def load_image_decisions(conn: psycopg.Connection, *, source: str, product_type: str,
                         base_dir: str) -> dict:
    rows = _read_csv_dicts(output_csv_path(base_dir, source, product_type))
    decisions = build_boss_decision_rows(rows)
    for d in decisions:
        upsert_image_decision(conn, d)
    return {"loaded": len(decisions)}
```

- [ ] **Step 4: 运行 `pytest tests/test_image_decisions.py -v`，确认全部 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/bridge/image_decisions.py tests/test_image_decisions.py
git commit -m "feat: load ERP image-search decisions into PG"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 3: CLI erp-image-load-db

**Files:** Modify `src/sourcing/cli.py`; Test: append to `tests/test_cli.py`.

- [ ] **Step 1: 修改 `src/sourcing/cli.py`** —
(a) imports 区加：`from sourcing.bridge.image_decisions import load_image_decisions`
(b) 子命令定义区加：
```python
    img_load = sub.add_parser("erp-image-load-db", help="把 ERP 图搜老板决策落进 PostgreSQL")
    img_load.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    img_load.add_argument("--product-type", required=True)
```
(c) 在连库后的 dispatch（与 analyze 同级）加：
```python
        elif args.command == "erp-image-load-db":
            summary = load_image_decisions(
                conn, source=args.source, product_type=args.product_type,
                base_dir=config.collect_base_dir())
            print(f"[DONE] image decisions loaded: {summary}")
```

- [ ] **Step 2: APPEND 测试到 `tests/test_cli.py`**

```python
def test_cli_erp_image_load_db(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-load-db", "--source", "ixspy", "--product-type", "bags",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "load_image_decisions",
        lambda conn, *, source, product_type, base_dir:
            calls.update(source=source, product_type=product_type, base_dir=base_dir) or {"loaded": 7},
    )
    cli.main()
    assert calls == {"source": "ixspy", "product_type": "bags", "base_dir": "/base518"}
```

- [ ] **Step 3: 验证 CLI 可导入：`python -c "import sourcing.cli; print('cli ok')"`。**

- [ ] **Step 4: 全量 `pytest -v`，确认无回归（新 CLI 用例通过）。**

- [ ] **Step 5: Commit**
```
git add src/sourcing/cli.py tests/test_cli.py
git commit -m "feat: cli erp-image-load-db subcommand"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 4: README + Metabase 卡片说明

**Files:** Modify `README.md`, `docs/metabase-dashboards.md`.

- [ ] **Step 1: 在 `docs/metabase-dashboards.md` 末尾追加一节**

````markdown
## 看板三：ERP 图搜查重决策
先把图搜结果落库：
```powershell
python -m sourcing.cli erp-image-search --source ixspy --product-type <品类> --limit 50
python -m sourcing.cli erp-image-load-db --source ixspy --product-type <品类>
```
给 metabase_ro 授权（执行一次）：
```sql
GRANT SELECT ON v_erp_image_decisions, erp_image_decisions TO metabase_ro;
```
Metabase 卡片 SQL：
```sql
SELECT external_sku, external_product_name, final_decision, boss_action,
       candidate_count, normal_candidate_count, top_erp_skus
FROM v_erp_image_decisions
ORDER BY is_new_opportunity DESC, candidate_count DESC;
```
按 `final_decision` 筛"疑似新品机会"即得过了 ERP 查重的真实新品候选。
````

- [ ] **Step 2: 在 `README.md` 的「看板（Metabase）」一节补一句**

```markdown
新增视图 `v_erp_image_decisions`（ERP 图搜查重决策）。流程：`erp-image-search` → `erp-image-load-db` → Metabase。
```

- [ ] **Step 3: Commit**
```
git add README.md docs/metabase-dashboards.md
git commit -m "docs: ERP image decisions dashboard usage"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Self-Review 结论
- **目标覆盖**：图搜决策落 PG（表 `erp_image_decisions`）→ 视图 `v_erp_image_decisions`（含 `is_new_opportunity` 标记）→ Metabase 卡片，和 v_opportunities 同套路。
- **复用**：直接用 `erp_image_search.build_boss_decision_rows`/`_read_csv_dicts`，不重写归纳逻辑；落库用 `base_dir=collect_base_dir()` 与图搜输出一致（避免之前 base_dir 坑）。
- **可测**：迁移结构测；落库用临时结果 CSV + PG conn 测（决策正确/新品机会标记/幂等）；CLI monkeypatch。不依赖真实 ERP/网络。
- **占位符**：无；SQL 与代码完整。
- **类型一致性**：`load_image_decisions(conn,*,source,product_type,base_dir)`、`upsert_image_decision`、视图列名跨任务/文档一致。
- **不依赖相似度**（ERP 响应不含），决策基于状态+候选数。
- **依赖**：erp_image_search 已合并；不改其行为，仅新增落库 + 表/视图 + CLI。
