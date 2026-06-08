ALTER TABLE erp_image_decisions ADD COLUMN max_embedding_similarity NUMERIC;

CREATE OR REPLACE VIEW v_erp_image_decisions AS
SELECT
    source, product_type, external_sku, external_product_name, external_product_url,
    external_image_url, final_decision, boss_action, candidate_count,
    normal_candidate_count, stopped_candidate_count, risk_candidate_count,
    top_erp_skus, top_main_skus,
    (final_decision = '疑似新品机会') AS is_new_opportunity,
    generated_at,
    max_embedding_similarity
FROM erp_image_decisions;
