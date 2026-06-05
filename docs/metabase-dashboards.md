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
Host=host.docker.internal（或宿主 IP），Port=5432，DB=sourcing，User=metabase_ro。

## 3. 看板一：选品机会
新建 SQL 问题，保存为卡片，加进一个 Dashboard：

机会榜（gap 优先、机会分倒序）：
```sql
SELECT platform, platform_product_id, title, category,
       opportunity_score, margin, profit_confidence,
       latest_price, latest_sales, review_rating
FROM v_opportunities
WHERE is_gap = true AND opportunity_score IS NOT NULL
ORDER BY opportunity_score DESC
LIMIT 200;
```
按类目的机会数量（柱状图）：
```sql
SELECT category, count(*) AS gap_count
FROM v_opportunities WHERE is_gap = true
GROUP BY category ORDER BY gap_count DESC LIMIT 20;
```
在 Dashboard 加筛选器：platform、category、margin 区间。

## 4. 看板二：竞品监控
```sql
SELECT own_title, own_sku, cost_price,
       competitor_title, competitor_platform, competitor_external_id,
       competitor_price, competitor_sales, final_score
FROM v_competitor_monitor
ORDER BY final_score DESC;
```
> 当前 518 匹配多为“ERP无对应”，confirmed 对为空属正常；518 人工确认后 `bridge-matches` 会让此看板有数据。

## 5. 刷新
看板读视图，数据随 collect / import-external / bridge-matches / analyze 更新而更新。

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
按 `final_decision` 筛“疑似新品机会”即得过了 ERP 查重的真实新品候选。
