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
