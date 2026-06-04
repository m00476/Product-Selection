CREATE TABLE raw_source_records (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          TEXT        NOT NULL,
    platform        TEXT        NOT NULL,
    product_type    TEXT        NOT NULL,
    source_file     TEXT        NOT NULL,
    source_record_id TEXT       NOT NULL,
    raw_payload     JSONB       NOT NULL,
    payload_hash    TEXT        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_raw UNIQUE (source, platform, source_record_id, collected_at)
);
CREATE INDEX idx_raw_lookup ON raw_source_records (source, platform, source_record_id);

CREATE TABLE collector_runs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        TEXT        NOT NULL,
    product_type  TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT        NOT NULL DEFAULT 'running',
    record_count  INTEGER     NOT NULL DEFAULT 0
);

CREATE TABLE collector_errors (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       BIGINT REFERENCES collector_runs(id),
    source       TEXT,
    detail       TEXT,
    raw_excerpt  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_cursors (
    source        TEXT NOT NULL,
    product_type  TEXT NOT NULL,
    last_synced_at TIMESTAMPTZ,
    cursor_value  TEXT,
    PRIMARY KEY (source, product_type)
);
