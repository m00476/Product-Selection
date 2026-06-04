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
