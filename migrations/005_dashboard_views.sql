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
