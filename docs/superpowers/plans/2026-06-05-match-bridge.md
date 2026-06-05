# 匹配桥接（Match Bridge，Plan 4A）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 518 项目已有的匹配结果（`518/data/app.db` 的 `match_results`）桥接进本系统 PostgreSQL 的新表 `product_matches`，按"竞品(platform+platform_product_id)↔自家(erp_sku)"映射，供后续 Metabase 看板使用。不重建匹配引擎。

**Architecture:** 薄桥接层。`reader`（用 sqlite3 读 518 app.db 的 match_results，纯读）+ `bridge`（把每条结果映射到 PG：按平台商品ID找竞品、按 erp_sku 找自家、upsert product_matches）+ CLI `bridge-matches` 子命令。518 的匹配/图像/人工复核完全复用，本层只搬运结果。

**Tech Stack:** Python 3.12（标准库 sqlite3）、psycopg 3、pytest、PostgreSQL 16。

参考设计：`docs/.../2026-06-04-product-sourcing-system-design.md` §4(`product_matches`)、§5(匹配)。

## 已核实事实（518 app.db）
- `match_results`(27286 行) 列：`platform, external_product_id, external_title, erp_product_id, erp_sku, image_score, title_score, category_score, price_score, final_score, match_status, fail_reason, matched_rank, created_at`。
- 当前真实行 `match_status` 多为"ERP里没有"(竞品在 ERP 无对应 = 选品机会)；`manual_reviews` 暂 0 行。桥接需对各种 `match_status` 都不报错。
- 映射键：`(platform, external_product_id)` → 本系统 `products(platform, platform_product_id)`；`erp_sku` → `erp_skus(sku)` → `own_product_id`。
- 本系统当前**没有** `product_matches` 表（Plan 1 只建了 `source_product_links`），本计划新建。

## File Structure
```
migrations/004_product_matches.sql       # 新建 product_matches 表
src/sourcing/bridge/__init__.py
src/sourcing/bridge/match_reader.py      # 读 518 app.db match_results（sqlite3）
src/sourcing/bridge/match_bridge.py      # 映射 + upsert 进 PG
src/sourcing/config.py                   # 增加 app_db_path()（修改）
src/sourcing/cli.py                      # 增加 bridge-matches 子命令（修改）
.env.example                             # 增加 APP_DB_PATH（修改）
tests/test_match_reader.py
tests/test_match_bridge.py
tests/test_cli.py                        # 追加 bridge-matches 用例（修改）
```

---

## Task 1: 迁移 004 — product_matches 表

**Files:** Create `migrations/004_product_matches.sql`; Test `tests/test_match_bridge.py`（先放结构测试）。

- [ ] **Step 1: 写失败测试 `tests/test_match_bridge.py`**

```python
def test_product_matches_table_exists(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('product_matches')")
        assert cur.fetchone()[0] is not None


def test_product_matches_upsert_by_unique_key(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon','900',false) RETURNING product_id")
        comp = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO product_matches (competitor_product_id, erp_sku, status, final_score) "
            "VALUES (%s,'SKU1','pending',10.0)", (comp,))
        cur.execute(
            "INSERT INTO product_matches (competitor_product_id, erp_sku, status, final_score) "
            "VALUES (%s,'SKU1','confirmed',20.0) "
            "ON CONFLICT (competitor_product_id, erp_sku) DO UPDATE SET "
            "status=EXCLUDED.status, final_score=EXCLUDED.final_score", (comp,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT status, final_score FROM product_matches WHERE competitor_product_id=%s", (comp,))
        assert cur.fetchone() == ("confirmed", 20.0)
        cur.execute("SELECT count(*) FROM product_matches")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行 `pytest tests/test_match_bridge.py -v`，确认 FAIL。**

- [ ] **Step 3: 创建 `migrations/004_product_matches.sql`**

```sql
CREATE TABLE product_matches (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    competitor_product_id BIGINT REFERENCES products(product_id),
    own_product_id        BIGINT REFERENCES products(product_id),
    erp_sku               TEXT NOT NULL DEFAULT '',
    match_source          TEXT NOT NULL DEFAULT '518',
    image_score           NUMERIC,
    title_score           NUMERIC,
    category_score        NUMERIC,
    price_score           NUMERIC,
    final_score           NUMERIC,
    raw_match_status      TEXT,
    status                TEXT NOT NULL DEFAULT 'pending',
    reasons               TEXT,
    bridged_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_match UNIQUE (competitor_product_id, erp_sku)
);
```

> 说明：`erp_sku` 用 `''` 而非 NULL 默认，使 `(competitor_product_id, erp_sku)` 唯一约束对"无 ERP 匹配"行也生效（避免重复）。`status` 是归一化状态（pending/confirmed/rejected/auto_confirmed/no_erp_match），`raw_match_status` 保留 518 原值。

- [ ] **Step 4: 运行 `pytest tests/test_match_bridge.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add migrations/004_product_matches.sql tests/test_match_bridge.py
git commit -m "feat: migration 004 product_matches"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 2: 读 518 app.db 的 match_results

**Files:** Create `src/sourcing/bridge/__init__.py` (empty), `src/sourcing/bridge/match_reader.py`; Test `tests/test_match_reader.py`.

- [ ] **Step 1: 写失败测试 `tests/test_match_reader.py`**（测试里临时建一个最小 sqlite 当作 518 app.db）

```python
import sqlite3
from sourcing.bridge.match_reader import read_match_results, MatchRow


def _make_app_db(path):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE match_results (
        id INTEGER PRIMARY KEY, platform TEXT, external_product_id TEXT,
        erp_sku TEXT, image_score REAL, title_score REAL, category_score REAL,
        price_score REAL, final_score REAL, match_status TEXT, fail_reason TEXT)""")
    c.execute("INSERT INTO match_results (platform, external_product_id, erp_sku, "
              "image_score, title_score, category_score, price_score, final_score, match_status) "
              "VALUES ('ozon','900','SKU1',0.8,0.7,0.6,0.5,12.3,'matched')")
    c.execute("INSERT INTO match_results (platform, external_product_id, erp_sku, "
              "final_score, match_status) VALUES ('aliexpress','1005','',5.0,'ERP里没有')")
    c.commit(); c.close()


def test_read_match_results(tmp_path):
    db = str(tmp_path / "app.db")
    _make_app_db(db)
    rows = read_match_results(db)
    assert len(rows) == 2
    assert isinstance(rows[0], MatchRow)
    assert rows[0].platform == "ozon"
    assert rows[0].external_product_id == "900"
    assert rows[0].erp_sku == "SKU1"
    assert rows[0].final_score == 12.3
    assert rows[0].match_status == "matched"
    assert rows[1].erp_sku == ""  # 空 sku 规范化为空串
    assert rows[1].match_status == "ERP里没有"
```

- [ ] **Step 2: 运行 `pytest tests/test_match_reader.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/bridge/__init__.py`（空）与 `src/sourcing/bridge/match_reader.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_match_reader.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/bridge/__init__.py src/sourcing/bridge/match_reader.py tests/test_match_reader.py
git commit -m "feat: read 518 app.db match_results"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 3: 映射 + upsert 进 PG（bridge）

**Files:** Create `src/sourcing/bridge/match_bridge.py`; Test: append to `tests/test_match_bridge.py`.

状态映射（518 `match_status` → 本系统 `status`）：
- 含"没有"/"no" → `no_erp_match`（竞品在 ERP 无对应 = 选品机会）
- "confirmed"/"matched" → `confirmed`
- "rejected" → `rejected`
- 其它/空 → `pending`

- [ ] **Step 1: APPEND 失败测试到 `tests/test_match_bridge.py`**

```python
from datetime import datetime, timezone
from sourcing.bridge.match_reader import MatchRow
from sourcing.bridge.match_bridge import normalize_status, bridge_rows


def test_normalize_status():
    assert normalize_status("ERP里没有") == "no_erp_match"
    assert normalize_status("matched") == "confirmed"
    assert normalize_status("confirmed") == "confirmed"
    assert normalize_status("rejected") == "rejected"
    assert normalize_status(None) == "pending"
    assert normalize_status("weird") == "pending"


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO products (platform, platform_product_id, is_own) "
                    "VALUES ('ozon','900',false) RETURNING product_id")
        comp = cur.fetchone()[0]
        cur.execute("INSERT INTO products (platform, is_own) VALUES ('erp', true) RETURNING product_id")
        own = cur.fetchone()[0]
        cur.execute("INSERT INTO erp_skus (sku, own_product_id) VALUES ('SKU1',%s)", (own,))
    conn.commit()
    return comp, own


def test_bridge_rows_maps_and_links(conn):
    comp, own = _seed(conn)
    rows = [
        MatchRow("ozon", "900", "SKU1", 0.8, 0.7, 0.6, 0.5, 12.3, "matched"),
        MatchRow("ozon", "404", "SKUX", None, None, None, None, 1.0, "matched"),  # 竞品不在本库 -> 跳过
    ]
    summary = bridge_rows(conn, rows)
    assert summary["bridged"] == 1
    assert summary["skipped_no_competitor"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT competitor_product_id, own_product_id, status, final_score "
                    "FROM product_matches")
        row = cur.fetchone()
        assert row == (comp, own, "confirmed", 12.3)


def test_bridge_no_erp_match_keeps_null_own(conn):
    comp, _ = _seed(conn)
    rows = [MatchRow("ozon", "900", "", None, None, None, None, 5.0, "ERP里没有")]
    bridge_rows(conn, rows)
    with conn.cursor() as cur:
        cur.execute("SELECT own_product_id, status FROM product_matches WHERE competitor_product_id=%s", (comp,))
        assert cur.fetchone() == (None, "no_erp_match")
```

- [ ] **Step 2: 运行 `pytest tests/test_match_bridge.py -v`，确认新测试 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/bridge/match_bridge.py`**

```python
import psycopg
from sourcing.bridge.match_reader import MatchRow


def normalize_status(raw: str | None) -> str:
    if not raw:
        return "pending"
    text = raw.strip().lower()
    if "没有" in raw or "no" in text:
        return "no_erp_match"
    if "confirm" in text or "match" in text:
        return "confirmed"
    if "reject" in text:
        return "rejected"
    return "pending"


def _find_competitor(conn, platform, external_product_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT product_id FROM products "
            "WHERE is_own = false AND platform = %s AND platform_product_id = %s",
            (platform, external_product_id),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _find_own(conn, erp_sku):
    if not erp_sku:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT own_product_id FROM erp_skus WHERE sku = %s", (erp_sku,))
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else None


def bridge_rows(conn: psycopg.Connection, rows: list[MatchRow]) -> dict:
    bridged = 0
    skipped = 0
    for r in rows:
        competitor_id = _find_competitor(conn, r.platform, r.external_product_id)
        if competitor_id is None:
            skipped += 1
            continue
        own_id = _find_own(conn, r.erp_sku)
        status = normalize_status(r.match_status)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO product_matches
                    (competitor_product_id, own_product_id, erp_sku, match_source,
                     image_score, title_score, category_score, price_score, final_score,
                     raw_match_status, status)
                VALUES (%s,%s,%s,'518',%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (competitor_product_id, erp_sku) DO UPDATE SET
                    own_product_id=EXCLUDED.own_product_id,
                    image_score=EXCLUDED.image_score, title_score=EXCLUDED.title_score,
                    category_score=EXCLUDED.category_score, price_score=EXCLUDED.price_score,
                    final_score=EXCLUDED.final_score, raw_match_status=EXCLUDED.raw_match_status,
                    status=EXCLUDED.status, bridged_at=now()
                """,
                (competitor_id, own_id, r.erp_sku, r.image_score, r.title_score,
                 r.category_score, r.price_score, r.final_score, r.match_status, status),
            )
        bridged += 1
    conn.commit()
    return {"bridged": bridged, "skipped_no_competitor": skipped}
```

- [ ] **Step 4: 运行 `pytest tests/test_match_bridge.py -v`，确认全部 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/bridge/match_bridge.py tests/test_match_bridge.py
git commit -m "feat: bridge 518 match_results into product_matches"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 4: 编排 + 配置 + CLI bridge-matches

**Files:** Create `src/sourcing/bridge/run.py`; Modify `src/sourcing/config.py`, `src/sourcing/cli.py`, `.env.example`; Test: append to `tests/test_cli.py`.

- [ ] **Step 1: 创建 `src/sourcing/bridge/run.py`**

```python
import psycopg
from sourcing.bridge.match_reader import read_match_results
from sourcing.bridge.match_bridge import bridge_rows


def bridge_matches(conn: psycopg.Connection, app_db_path: str) -> dict:
    rows = read_match_results(app_db_path)
    summary = bridge_rows(conn, rows)
    summary["read"] = len(rows)
    return summary
```

- [ ] **Step 2: 在 `src/sourcing/config.py` 末尾追加**

```python
def app_db_path() -> str:
    return os.environ.get("APP_DB_PATH", r"C:\Users\aibp\Desktop\518\data\app.db")
```

- [ ] **Step 3: 在 `.env.example` 末尾追加**

```text
# 匹配桥接：518 项目的 SQLite 匹配库
APP_DB_PATH=C:\Users\aibp\Desktop\518\data\app.db
```

- [ ] **Step 4: 修改 `src/sourcing/cli.py`** — 增加 `bridge-matches` 子命令。在 imports 区加 `from sourcing.bridge.run import bridge_matches`；在子命令定义区加：

```python
    sub.add_parser("bridge-matches", help="把 518 匹配结果桥接进 product_matches")
```

并在 `args.command` 分发里（与 analyze 同级）加：

```python
        elif args.command == "bridge-matches":
            summary = bridge_matches(conn, config.app_db_path())
            print(f"[DONE] bridged: {summary}")
```

- [ ] **Step 5: APPEND 测试到 `tests/test_cli.py`**

```python
def test_cli_bridge_matches(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", ["sourcing.cli", "bridge-matches"])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "app_db_path", lambda: "/x/app.db")
    monkeypatch.setattr(
        cli, "bridge_matches",
        lambda conn, path: calls.update(path=path) or {"bridged": 3, "read": 5},
    )
    cli.main()
    assert calls["path"] == "/x/app.db"
```

- [ ] **Step 6: 验证 CLI 可导入：`python -c "import sourcing.cli; print('cli ok')"`，期望 `cli ok`。**

- [ ] **Step 7: 全量 `pytest -v`，确认无回归（新 CLI 用例通过）。**

- [ ] **Step 8: Commit**
```
git add src/sourcing/bridge/run.py src/sourcing/config.py src/sourcing/cli.py .env.example tests/test_cli.py
git commit -m "feat: cli bridge-matches subcommand"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 5: README — 桥接说明

**Files:** Modify `README.md`.

- [ ] **Step 1: 在 README「采集」一节后插入：**

````markdown
## 匹配桥接（复用 518 的匹配结果）
518 项目用 DINOv2/FAISS+文本相似度做匹配，结果在 `518/data/app.db`。本命令把
`match_results` 桥接进本系统 `product_matches`（按 平台商品ID/erp_sku 映射）：
```powershell
python -m sourcing.cli bridge-matches
```
配置 `.env` 的 `APP_DB_PATH` 指向 518 的 app.db。`status` 取值：`confirmed`（已匹配自家SKU）、
`no_erp_match`（竞品在 ERP 无对应 = 选品机会）、`pending`/`rejected`。
````

- [ ] **Step 2: Commit**
```
git add README.md
git commit -m "docs: bridge-matches usage"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Self-Review 结论
- **Spec 覆盖**：§4 `product_matches` 表本计划新建；§5 匹配复用 518（不重建），桥接其结果并保留分数/状态/原因。
- **可测性**：reader 用临时 sqlite fixture 测；bridge 用 PG conn + 种子数据测（映射成功/竞品不在库跳过/无ERP匹配三路径）；CLI monkeypatch。全程可测，不依赖 518 真实库。
- **占位符**：无 TODO/TBD；所有代码步骤含完整可执行代码。
- **类型一致性**：`MatchRow`、`read_match_results`、`normalize_status`、`bridge_rows`、`bridge_matches`、`config.app_db_path` 跨任务一致。
- **已知边界**：当前 518 真实匹配多为"ERP里没有"(→ no_erp_match)，正向匹配待 518 跑出/人工确认后再桥接即自动生效；桥接是幂等 upsert，可反复跑。Metabase 看板属 Plan 4B。
- **依赖**：Plan 1 的 `products`/`erp_skus` 就绪；新增 `bridge` 包 + `product_matches` 表，不改既有模块行为。
