CREATE TABLE products (
    product_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform            TEXT        NOT NULL,
    platform_product_id TEXT,
    title               TEXT,
    category            TEXT,
    image_url           TEXT,
    brand               TEXT,
    seller_id           TEXT,
    seller_name         TEXT,
    is_own              BOOLEAN     NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_products_competitor
    ON products (platform, platform_product_id)
    WHERE is_own = false AND platform_product_id IS NOT NULL;

CREATE TABLE erp_skus (
    sku             TEXT PRIMARY KEY,
    own_product_id  BIGINT REFERENCES products(product_id),
    cost_price          NUMERIC,
    weighted_purchase   NUMERIC,
    weighted_freight    NUMERIC,
    weighted_sorting    NUMERIC,
    stock               INTEGER,
    once_gross_margin   NUMERIC,
    main_platform       TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_product_links (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source               TEXT NOT NULL,
    source_record_id     TEXT NOT NULL,
    raw_source_record_id BIGINT REFERENCES raw_source_records(id),
    platform             TEXT NOT NULL,
    platform_product_id  TEXT,
    canonical_url        TEXT,
    product_id           BIGINT REFERENCES products(product_id),
    link_type            TEXT NOT NULL DEFAULT 'deterministic',
    confidence           NUMERIC NOT NULL DEFAULT 1.0,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_link UNIQUE (source, source_record_id)
);

CREATE TABLE price_snapshots (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id           BIGINT REFERENCES products(product_id),
    source               TEXT NOT NULL,
    platform             TEXT NOT NULL,
    platform_product_id  TEXT,
    price                NUMERIC,
    currency             TEXT,
    observed_at          TIMESTAMPTZ NOT NULL,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_source        TEXT,
    raw_source_record_id BIGINT REFERENCES raw_source_records(id),
    CONSTRAINT uq_price UNIQUE (source, platform, platform_product_id, observed_at)
);

CREATE TABLE sales_snapshots (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id           BIGINT REFERENCES products(product_id),
    source               TEXT NOT NULL,
    platform             TEXT NOT NULL,
    platform_product_id  TEXT,
    sales                NUMERIC,
    review_count         INTEGER,
    review_rating        NUMERIC,
    observed_at          TIMESTAMPTZ NOT NULL,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_source        TEXT,
    raw_source_record_id BIGINT REFERENCES raw_source_records(id),
    CONSTRAINT uq_sales UNIQUE (source, platform, platform_product_id, observed_at)
);

CREATE TABLE reviews (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id   BIGINT REFERENCES products(product_id),
    source       TEXT,
    rating       NUMERIC,
    content      TEXT,
    observed_at  TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
