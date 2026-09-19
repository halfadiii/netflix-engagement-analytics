-- Trailer views against engagement, for the 20 hand-matched titles from 2026H1.
--
-- Run scripts/fetch_trailers.py, which fills fact_trailer_engagement and then
-- runs this. The counts are not committed: YouTube's policies cap storing them
-- at 30 days, so they only ever exist in the local, gitignored database.
--
-- Compared within content type on purpose. Film trailers draw far more views
-- than series trailers at similar viewing levels, so mixing the two would
-- mostly measure the film/series split, not trailer interest.
--
-- Read this as a correlation over 20 titles and nothing more. View counts are
-- cumulative to the day they were fetched, and a title that becomes a hit sends
-- people back to its trailer, so the arrow can point either way.

WITH latest AS (
    SELECT *
    FROM fact_trailer_engagement
    WHERE fetched_at = (SELECT MAX(fetched_at) FROM fact_trailer_engagement)
),
chart AS (
    SELECT title_id,
           MIN(weekly_rank)         AS peak_global_rank,
           COUNT(DISTINCT date_key) AS weeks_in_global_top10
    FROM fact_top10_weekly
    WHERE region_id = (SELECT region_id FROM dim_region WHERE region_name = 'Global')
    GROUP BY title_id
)
SELECT
    d.title_name,
    d.content_type,
    t.view_count                                                        AS trailer_views,
    CAST(julianday(t.fetched_at) - julianday(t.published_at) AS INTEGER) AS days_since_trailer,
    ROUND(f.hours_viewed / 1e6, 1)                                      AS hours_viewed_million,
    c.peak_global_rank,
    c.weeks_in_global_top10,
    RANK() OVER (PARTITION BY d.content_type ORDER BY t.view_count DESC)   AS trailer_rank_in_type,
    RANK() OVER (PARTITION BY d.content_type ORDER BY f.hours_viewed DESC) AS hours_rank_in_type
FROM latest t
JOIN dim_title d            ON d.title_id = t.title_id
-- The release-date condition is load-bearing: dim_title keys on (name, type),
-- so two different works with the same name share a title_id. "War Machine"
-- is the 2026 film and an older one, both in 2026H1. Every title here was
-- released in 2026H1, so that picks the right row.
JOIN fact_engagement_half f ON f.title_id = t.title_id AND f.period_label = '2026H1'
                            AND f.release_date >= '2026-01-01'
LEFT JOIN chart c           ON c.title_id = t.title_id
ORDER BY d.content_type, t.view_count DESC
