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
