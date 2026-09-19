-- Star schema (fact constellation) for the Netflix engagement analytics project.
-- Two fact tables share the same conformed dimensions because the two public
-- source datasets have different grains:
--   fact_top10_weekly    -> title x week x region   (rank always present, hours only for Global)
--   fact_engagement_half -> title x half-year        (real hours viewed, ~99% of all platform viewing, Global only)
--
-- This file documents the logical model. The physical tables are created by
-- scripts/build_star_schema.py (pandas -> SQLite) with the same columns/types.

CREATE TABLE dim_date (
    date_key    TEXT PRIMARY KEY,      -- 'YYYY-MM-DD', week-start Sunday for weekly facts, period-start for half facts
    full_date   TEXT NOT NULL,
    year        INTEGER NOT NULL,
    quarter     INTEGER NOT NULL,
    half_label  TEXT NOT NULL,         -- e.g. '2026H1'
    month       INTEGER NOT NULL,
    month_name  TEXT NOT NULL,
    iso_week    INTEGER NOT NULL
);

CREATE TABLE dim_title (
    title_id     INTEGER PRIMARY KEY,
    title_name   TEXT NOT NULL,
    content_type TEXT NOT NULL         -- 'Show' | 'Movie'
);

CREATE TABLE dim_region (
    region_id   INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL,         -- 'Global' or a country name
    iso2        TEXT,                  -- NULL for 'Global'
    is_global   INTEGER NOT NULL       -- 1/0
);

CREATE TABLE fact_top10_weekly (
    date_key                  TEXT REFERENCES dim_date(date_key),
    title_id                  INTEGER REFERENCES dim_title(title_id),
    region_id                 INTEGER REFERENCES dim_region(region_id),
    content_type              TEXT,
    language                  TEXT,     -- 'English' | 'Non-English' (Global rows only)
    weekly_rank                INTEGER,
    hours_viewed               INTEGER, -- populated for region = 'Global' only
    views                       REAL,   -- populated for region = 'Global' only
    cumulative_weeks_in_top10  INTEGER
);

CREATE TABLE fact_engagement_half (
    date_key               TEXT REFERENCES dim_date(date_key),  -- period start date
    title_id               INTEGER REFERENCES dim_title(title_id),
    content_type           TEXT,
    period_label           TEXT,        -- '2025H1' | '2025H2' | '2026H1'
    is_available_globally  TEXT,
    release_date           TEXT,
    hours_viewed           REAL,
    views                  REAL,
    runtime_minutes        REAL
);
