-- KPI / analysis layer for the Netflix engagement analytics project.
-- Run against data/netflix_engagement.db (SQLite). Mirrors the 5 framing
-- questions in README.md. Window functions are used wherever the JD's
-- "trend / ranking logic" language points to them (LAG, RANK, SUM OVER).

-- ============================================================
-- Q0. Top-line KPIs (the KPI row of the dashboard)
-- ============================================================
SELECT
    period_label,
    COUNT(DISTINCT title_id)                  AS titles_tracked,
    ROUND(SUM(hours_viewed) / 1e9, 2)          AS total_hours_billion,
    ROUND(AVG(hours_viewed) / 1e6, 2)          AS avg_hours_per_title_million
FROM fact_engagement_half
GROUP BY period_label
ORDER BY period_label;


-- ============================================================
-- Q1. What's driving engagement hours? -> top titles by hours,
--     and the cumulative share the top N titles contribute (concentration)
-- ============================================================
WITH ranked AS (
    SELECT
        f.period_label,
        d.title_name,
        f.content_type,
        f.hours_viewed,
        RANK() OVER (PARTITION BY f.period_label ORDER BY f.hours_viewed DESC) AS rank_in_period,
        SUM(f.hours_viewed) OVER (PARTITION BY f.period_label ORDER BY f.hours_viewed DESC
                                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_hours,
        SUM(f.hours_viewed) OVER (PARTITION BY f.period_label) AS period_total_hours
    FROM fact_engagement_half f
    JOIN dim_title d ON d.title_id = f.title_id
)
SELECT
    period_label, rank_in_period, title_name, content_type,
    ROUND(hours_viewed / 1e6, 1)                       AS hours_viewed_million,
    ROUND(100.0 * running_hours / period_total_hours,2) AS cumulative_pct_of_total_hours
FROM ranked
WHERE rank_in_period <= 10
ORDER BY period_label, rank_in_period;


-- ============================================================
-- Q2. Which content types perform best? -> Show vs Movie, English vs Non-English
-- ============================================================
SELECT
    period_label,
    content_type,
    ROUND(SUM(hours_viewed) / 1e9, 2)                                       AS hours_billion,
    ROUND(100.0 * SUM(hours_viewed) / SUM(SUM(hours_viewed)) OVER (PARTITION BY period_label), 1) AS pct_of_period_hours,
    ROUND(AVG(hours_viewed) / 1e6, 2)                                       AS avg_hours_per_title_million,
    COUNT(*)                                                                AS titles
FROM fact_engagement_half
GROUP BY period_label, content_type
ORDER BY period_label, content_type;

-- English vs Non-English split, Global weekly Top 10 only (language flag lives in fact_top10_weekly)
SELECT
    language,
    content_type,
    ROUND(SUM(hours_viewed) / 1e9, 2) AS hours_billion,
    COUNT(DISTINCT title_id)          AS distinct_titles_in_top10
FROM fact_top10_weekly
WHERE region_id = (SELECT region_id FROM dim_region WHERE region_name = 'Global')
GROUP BY language, content_type
ORDER BY hours_billion DESC;


-- ============================================================
-- Q3. How does engagement trend over time? -> half-over-half growth (LAG)
-- ============================================================
WITH totals AS (
    SELECT period_label, SUM(hours_viewed) AS total_hours
    FROM fact_engagement_half
    GROUP BY period_label
)
SELECT
    period_label,
    ROUND(total_hours / 1e9, 2)                                            AS total_hours_billion,
    ROUND((total_hours - LAG(total_hours) OVER (ORDER BY period_label)) / 1e9, 2) AS change_vs_prior_half_billion,
    ROUND(100.0 * (total_hours - LAG(total_hours) OVER (ORDER BY period_label))
          / LAG(total_hours) OVER (ORDER BY period_label), 2)              AS pct_change_vs_prior_half
FROM totals
ORDER BY period_label;

-- Weekly trend (Global Top 10 only, last 26 weeks) for a finer-grained trend line
WITH weekly AS (
    SELECT date_key, SUM(hours_viewed) AS weekly_hours
    FROM fact_top10_weekly
    WHERE region_id = (SELECT region_id FROM dim_region WHERE region_name = 'Global')
    GROUP BY date_key
)
SELECT
    date_key,
    ROUND(weekly_hours / 1e6, 1) AS weekly_hours_million,
    ROUND(AVG(weekly_hours) OVER (ORDER BY date_key ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) / 1e6, 1) AS trailing_4wk_avg_million
FROM weekly
ORDER BY date_key DESC
LIMIT 26;


-- ============================================================
-- Q4. Where is engagement concentrated? Every country fills exactly 10 Films +
--     10 TV slots every week, so raw appearance counts are identical everywhere
--     and useless as a concentration signal. Two real proxies instead:
--       (a) "stickiness" - how long titles stay in a country's Top 10 (repeat
--           viewing of the same titles vs. fast catalog turnover)
--       (b) "global alignment" - how often a country's #1 title matches the
--           Global English-language #1 for the same content type (i.e. does
--           this market track worldwide hits, or watch something different?)
-- ============================================================

-- (a) stickiness by country
SELECT
    r.region_name,
    r.iso2,
    ROUND(AVG(f.cumulative_weeks_in_top10), 2) AS avg_weeks_a_title_sticks_in_top10,
    COUNT(DISTINCT f.title_id)                 AS distinct_titles_ever_in_top10
FROM fact_top10_weekly f
JOIN dim_region r ON r.region_id = f.region_id
WHERE r.is_global = 0
GROUP BY r.region_name, r.iso2
ORDER BY avg_weeks_a_title_sticks_in_top10 DESC
LIMIT 15;

-- (b) global alignment by country (content_type = 'Show', most recent 52 weeks)
WITH global_no1 AS (
    SELECT date_key, content_type, title_id AS global_title_id
    FROM fact_top10_weekly
    WHERE region_id = (SELECT region_id FROM dim_region WHERE region_name = 'Global')
      AND weekly_rank = 1 AND language = 'English'
),
country_no1 AS (
    SELECT f.date_key, f.content_type, f.title_id AS country_title_id, r.region_name
    FROM fact_top10_weekly f
    JOIN dim_region r ON r.region_id = f.region_id
    WHERE r.is_global = 0 AND f.weekly_rank = 1
      AND f.date_key >= (SELECT date(MAX(date_key), '-364 days') FROM fact_top10_weekly)
)
SELECT
    c.region_name,
    c.content_type,
    ROUND(100.0 * SUM(CASE WHEN c.country_title_id = g.global_title_id THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_weeks_matching_global_no1,
    COUNT(*) AS weeks_compared
FROM country_no1 c
JOIN global_no1 g ON g.date_key = c.date_key AND g.content_type = c.content_type
GROUP BY c.region_name, c.content_type
ORDER BY pct_weeks_matching_global_no1 DESC
LIMIT 15;


-- ============================================================
-- Q5. Top / bottom movers by region -> rank change week-over-week (LAG + window)
-- ============================================================
-- NOTE: the LAG window must run over full history BEFORE filtering to the
-- latest week - filtering to one date_key first would leave one row per
-- (region, title) partition and LAG would always return NULL.
WITH ranked AS (
    SELECT
        f.region_id, r.region_name, f.title_id, d.title_name, f.date_key, f.weekly_rank,
        LAG(f.weekly_rank) OVER (PARTITION BY f.region_id, f.title_id ORDER BY f.date_key) AS prior_week_rank,
        LAG(f.date_key) OVER (PARTITION BY f.region_id, f.title_id ORDER BY f.date_key) AS prior_date_key
    FROM fact_top10_weekly f
    JOIN dim_region r ON r.region_id = f.region_id
    JOIN dim_title d ON d.title_id = f.title_id
)
SELECT
    region_name, title_name, weekly_rank, prior_week_rank,
    (prior_week_rank - weekly_rank) AS rank_improvement   -- positive = moved up the chart
FROM ranked
WHERE date_key = (SELECT MAX(date_key) FROM fact_top10_weekly)
  AND prior_week_rank IS NOT NULL
  AND prior_date_key = date(date_key, '-7 days')          -- only count consecutive weeks, not comeback re-entries
ORDER BY rank_improvement DESC
LIMIT 15;
