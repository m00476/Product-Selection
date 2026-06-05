# Metabase 看板（Plan 4B）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在 PostgreSQL 上建**去重好的 SQL 视图**（选品机会榜、竞品监控），并用 runbook + 现成 SQL 把 Metabase 两个看板搭起来：①选品机会看板 ②竞品监控看板。

**Architecture:** 数据层用 SQL 视图把分散的 products/快照/机会分/利润/匹配聚合成"一行一竞品"的看板友好结构（解决 product_matches 一竞品多行的重复放大）。展示层用 Metabase（docker-compose 已含）连 PG，基于视图建卡片。视图可 TDD；Metabase 卡片用 runbook + 可直接粘贴的 SQL。

**Tech Stack:** PostgreSQL 视图、psycopg、pytest、Metabase(Docker)。

参考设计：§4④ 看板、§6 两个看板。依赖已合并：products、price/sales_snapshots、opportunity_scores、profit_estimates、product_matches、erp_skus。

## 关键设计点
- **去重**：`product_matches` 对每个竞品可能多行（多候选 erp_sku）。视图里用 `NOT EXISTS(...confirmed...)` 得到每竞品一个 `is_gap` 布尔，不 join 明细，保证选品机会榜一行一竞品。
- **选品机会** = 竞品(is_own=false) + 机会分 + 利润 + 最新价/销量 + `is_gap`(ERP无确认匹配)。
- **竞品监控** = 已确认匹配(status=confirmed)的 自家↔竞品 对照（当前为空，结构就绪，518 确认后自动有数据）。

## File Structure
```
migrations/005_dashboard_views.sql       # v_opportunities + v_competitor_monitor 视图
docs/metabase-dashboards.md              # Metabase 搭建 runbook + 现成 SQL
README.md                                # 增加看板入口（修改）
tests/test_dashboard_views.py
```

---

## Task 1: 迁移 005 — 看板视图

**Files:** Create `migrations/005_dashboard_views.sql`; Test `tests/test_dashboard_views.py`.

- [ ] **Step 1: 写失败测试 `tests/test_dashboard_views.py`**

```python
from datetime import datetime, timezone


def _seed(conn):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        # 竞品A：有机会分 + 多条 no_erp_match 匹配（测去重）
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('ozon','900','Comp A',false) RETURNING product_id")
        a = cur.fetchone()[0]
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'seerfar','ozon','900',100.0,%s)", (a, now))
        cur.execute("INSERT INTO sales_snapshots (product_id, source, platform, platform_product_id, sales, review_rating, observed_at) "
                    "VALUES (%s,'seerfar','ozon','900',500,4.5,%s)", (a, now))
        cur.execute("INSERT INTO opportunity_scores (product_id, score, reason) VALUES (%s,0.42,'r')", (a,))
        cur.execute("INSERT INTO product_matches (competitor_product_id, erp_sku, status) VALUES (%s,'S1','no_erp_match')", (a,))
        cur.execute("INSERT INTO product_matches (competitor_product_id, erp_sku, status) VALUES (%s,'S2','no_erp_match')", (a,))
        # 竞品B：有一条 confirmed 匹配到自家
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('ozon','901','Comp B',false) RETURNING product_id")
        b = cur.fetchone()[0]
        cur.execute("INSERT INTO products (platform, title, is_own) VALUES ('erp','Own X',true) RETURNING product_id")
        own = cur.fetchone()[0]
        cur.execute("INSERT INTO erp_skus (sku, own_product_id, cost_price) VALUES ('SKUOWN',%s,30.0)", (own,))
        cur.execute("INSERT INTO product_matches (competitor_product_id, own_product_id, erp_sku, status, final_score) "
                    "VALUES (%s,%s,'SKUOWN','confirmed',55.0)", (b, own))
        cur.execute("INSERT INTO price_snapshots (product_id, source, platform, platform_product_id, price, observed_at) "
                    "VALUES (%s,'seerfar','ozon','901',88.0,%s)", (b, now))
    conn.commit()
    return a, b, own


def test_v_opportunities_one_row_per_competitor_and_gap(conn):
    a, b, _ = _seed(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT product_id, opportunity_score, latest_price, latest_sales, is_gap "
                    "FROM v_opportunities WHERE product_id=%s", (a,))
        rows = cur.fetchall()
        assert len(rows) == 1  # 多条匹配不放大
        pid, score, price, sales, is_gap = rows[0]
        assert float(score) == 0.42
        assert float(price) == 100.0
        assert float(sales) == 500
        assert is_gap is True   # 无 confirmed 匹配 = 机会
        # 竞品B 有 confirmed 匹配 -> 非 gap
        cur.execute("SELECT is_gap FROM v_opportunities WHERE product_id=%s", (b,))
        assert cur.fetchone()[0] is False


def test_v_competitor_monitor_shows_confirmed_pairs(conn):
    a, b, own = _seed(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT own_product_id, own_sku, cost_price, competitor_product_id, "
                    "competitor_price, final_score FROM v_competitor_monitor")
        rows = cur.fetchall()
    assert len(rows) == 1  # 只有竞品B 的 confirmed 对
    own_id, sku, cost, comp_id, comp_price, score = rows[0]
    assert own_id == own and sku == "SKUOWN" and comp_id == b
    assert float(comp_price) == 88.0 and float(score) == 55.0
```

- [ ] **Step 2: 运行 `pytest tests/test_dashboard_views.py -v`，确认 FAIL（视图不存在）。**

- [ ] **Step 3: 创建 `migrations/005_dashboard_views.sql`**

```sql
CREATE VIEW v_opportunities AS
SELECT
    p.product_id,
    p.platform,
    p.platform_product_id,
    p.title,
    p.category,
    p.image_url,
    os.score        AS opportunity_score,
    os.reason       AS opportunity_reason,
    pe.margin,
    pe.profit,
    pe.confidence   AS profit_confidence,
    lp.price        AS latest_price,
    ls.sales        AS latest_sales,
    ls.review_rating,
    NOT EXISTS (
        SELECT 1 FROM product_matches pm
        WHERE pm.competitor_product_id = p.product_id AND pm.status = 'confirmed'
    ) AS is_gap
FROM products p
LEFT JOIN opportunity_scores os ON os.product_id = p.product_id
LEFT JOIN profit_estimates pe ON pe.product_id = p.product_id
LEFT JOIN LATERAL (
    SELECT price FROM price_snapshots ps
    WHERE ps.product_id = p.product_id
    ORDER BY collected_at DESC, observed_at DESC LIMIT 1
) lp ON true
LEFT JOIN LATERAL (
    SELECT sales, review_rating FROM sales_snapshots ss
    WHERE ss.product_id = p.product_id
    ORDER BY collected_at DESC, observed_at DESC LIMIT 1
) ls ON true
WHERE p.is_own = false;

CREATE VIEW v_competitor_monitor AS
SELECT
    own.product_id           AS own_product_id,
    own.title                AS own_title,
    e.sku                    AS own_sku,
    e.cost_price,
    comp.product_id          AS competitor_product_id,
    comp.platform            AS competitor_platform,
    comp.platform_product_id AS competitor_external_id,
    comp.title               AS competitor_title,
    pm.final_score,
    clp.price                AS competitor_price,
    cls.sales                AS competitor_sales
FROM product_matches pm
JOIN products comp ON comp.product_id = pm.competitor_product_id
JOIN products own  ON own.product_id = pm.own_product_id
LEFT JOIN erp_skus e ON e.own_product_id = own.product_id
LEFT JOIN LATERAL (
    SELECT price FROM price_snapshots ps
    WHERE ps.product_id = comp.product_id
    ORDER BY collected_at DESC, observed_at DESC LIMIT 1
) clp ON true
LEFT JOIN LATERAL (
    SELECT sales FROM sales_snapshots ss
    WHERE ss.product_id = comp.product_id
    ORDER BY collected_at DESC, observed_at DESC LIMIT 1
) cls ON true
WHERE pm.status = 'confirmed';
```

- [ ] **Step 4: 运行 `pytest tests/test_dashboard_views.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add migrations/005_dashboard_views.sql tests/test_dashboard_views.py
git commit -m "feat: migration 005 dashboard views (opportunities + competitor monitor)"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 2: Metabase 搭建 runbook + 现成 SQL

**Files:** Create `docs/metabase-dashboards.md`; Modify `README.md`.

- [ ] **Step 1: 创建 `docs/metabase-dashboards.md`**

````markdown
# Metabase 看板搭建

## 1. 起 Metabase
```powershell
docker compose up -d metabase
```
浏览器开 http://localhost:3000 ，首次按引导建管理员账号。

## 2. 连接数据库（只读账号）
建议给 Metabase 一个只读账号（不暴露原始层 raw_source_records）。在 PG 执行一次：
```sql
CREATE ROLE metabase_ro LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE sourcing TO metabase_ro;
GRANT USAGE ON SCHEMA public TO metabase_ro;
GRANT SELECT ON v_opportunities, v_competitor_monitor,
    products, price_snapshots, sales_snapshots, opportunity_scores,
    profit_estimates, product_matches, erp_skus TO metabase_ro;
-- 不授予 raw_source_records，避免原始数据经看板外泄
```
在 Metabase: Admin → Databases → Add → PostgreSQL：
Host=postgres（容器内）或 host.docker.internal，Port=5432，DB=sourcing，User=metabase_ro。

## 3. 看板一：选品机会
新建 SQL 问题，依次保存为卡片，加进一个 Dashboard：

**机会榜（gap 优先、机会分倒序）：**
```sql
SELECT platform, platform_product_id, title, category,
       opportunity_score, margin, profit_confidence,
       latest_price, latest_sales, review_rating
FROM v_opportunities
WHERE is_gap = true AND opportunity_score IS NOT NULL
ORDER BY opportunity_score DESC
LIMIT 200;
```
**按类目的机会数量（柱状图）：**
```sql
SELECT category, count(*) AS gap_count
FROM v_opportunities WHERE is_gap = true
GROUP BY category ORDER BY gap_count DESC LIMIT 20;
```
在 Dashboard 加筛选器：platform、category、margin 区间（映射到卡片字段）。

## 4. 看板二：竞品监控
```sql
SELECT own_title, own_sku, cost_price,
       competitor_title, competitor_platform, competitor_external_id,
       competitor_price, competitor_sales, final_score
FROM v_competitor_monitor
ORDER BY final_score DESC;
```
> 当前 518 匹配多为"ERP无对应"，confirmed 对为空属正常；518 人工确认后 `bridge-matches` 会让此看板有数据。

## 5. 刷新
看板读视图，数据随 collect/import-external/bridge-matches/analyze 更新而更新。可在 Metabase 设卡片自动刷新或定时。
````

- [ ] **Step 2: 在 `README.md` 末尾（测试一节前后）加看板入口：**

````markdown
## 看板（Metabase）
SQL 视图 `v_opportunities`（选品机会）、`v_competitor_monitor`（竞品监控）已就绪。
搭建步骤见 `docs/metabase-dashboards.md`。
```powershell
docker compose up -d metabase   # http://localhost:3000
```
````

- [ ] **Step 3: Commit**
```
git add docs/metabase-dashboards.md README.md
git commit -m "docs: Metabase dashboards runbook + ready-to-use SQL"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Self-Review 结论
- **Spec 覆盖**：§6 两个看板 → v_opportunities(选品机会) + v_competitor_monitor(竞品监控)；§4 Metabase 展示层 → runbook。去重要求（一竞品一行）由 `NOT EXISTS confirmed` 实现并测试。Metabase 只读账号不授 raw_source_records，符合 §4 权限边界。
- **可测性**：视图用种子数据测（去重、is_gap、confirmed 对照三点）。Metabase 卡片是 GUI/配置，用 runbook + 可直接粘贴 SQL 覆盖，不强行 TDD。
- **占位符**：无 TODO/TBD；视图 SQL 完整；runbook 含可执行 SQL。
- **类型一致性**：视图列名稳定（opportunity_score/is_gap/latest_price 等），runbook SQL 与视图列一致。
- **已知边界**：竞品监控当前空（无 confirmed 匹配），结构就绪；机会榜立即有数据（22251 gap 竞品 + 机会分）。`metabase_ro` 角色是集群级，建在真实库执行（不入迁移，迁移只跑视图）。
- **依赖**：所有上游表/分析表已就绪；本计划只加视图 + 文档，不改既有代码行为。
