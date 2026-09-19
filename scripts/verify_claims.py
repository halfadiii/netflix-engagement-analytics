import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
conn = sqlite3.connect("data/netflix_engagement.db")
cur = conn.cursor()

print("--- markets where 'The Gentlemen: Season 1' climbed in the premiere week ---")
rows = cur.execute(
    """
    WITH ranked AS (
        SELECT r.region_name, d.title_name, f.date_key, f.weekly_rank,
               LAG(f.weekly_rank) OVER (PARTITION BY f.region_id, f.title_id ORDER BY f.date_key) AS prior_rank,
               LAG(f.date_key)    OVER (PARTITION BY f.region_id, f.title_id ORDER BY f.date_key) AS prior_date
        FROM fact_top10_weekly f
        JOIN dim_region r ON r.region_id = f.region_id
        JOIN dim_title  d ON d.title_id  = f.title_id
        WHERE r.is_global = 0
    )
    SELECT region_name, weekly_rank, prior_rank, (prior_rank - weekly_rank) AS improvement
    FROM ranked
    WHERE title_name = 'The Gentlemen: Season 1'
      AND date_key = (SELECT MAX(date_key) FROM fact_top10_weekly)
      AND prior_rank IS NOT NULL
      AND prior_date = date(date_key, '-7 days')
      AND prior_rank > weekly_rank
    ORDER BY improvement DESC
    """
).fetchall()
for r in rows:
    print(r)
print(f"TOTAL markets where it climbed: {len(rows)}")
if rows:
    print(f"improvement range: {min(r[3] for r in rows)} to {max(r[3] for r in rows)}")

print()
print("--- also: markets where it re-entered (no chart position the prior week) ---")
reentry = cur.execute(
    """
    WITH ranked AS (
        SELECT r.region_name, d.title_name, f.date_key, f.weekly_rank,
               LAG(f.date_key) OVER (PARTITION BY f.region_id, f.title_id ORDER BY f.date_key) AS prior_date
        FROM fact_top10_weekly f
        JOIN dim_region r ON r.region_id = f.region_id
        JOIN dim_title  d ON d.title_id  = f.title_id
        WHERE r.is_global = 0
    )
    SELECT COUNT(*)
    FROM ranked
    WHERE title_name = 'The Gentlemen: Season 1'
      AND date_key = (SELECT MAX(date_key) FROM fact_top10_weekly)
      AND (prior_date IS NULL OR prior_date <> date(date_key, '-7 days'))
    """
).fetchone()
print(f"re-entered from outside the chart in {reentry[0]} markets")

print()
print("--- hours per title, Show vs Movie, 2026H1 ---")
for row in cur.execute(
    """
    SELECT content_type,
           ROUND(AVG(hours_viewed) / 1e6, 2) AS avg_m,
           COUNT(*) AS titles
    FROM fact_engagement_half WHERE period_label = '2026H1'
    GROUP BY content_type
    """
):
    print(row)
ratio = cur.execute(
    """
    SELECT ROUND(
      (SELECT AVG(hours_viewed) FROM fact_engagement_half WHERE period_label='2026H1' AND content_type='Show') /
      (SELECT AVG(hours_viewed) FROM fact_engagement_half WHERE period_label='2026H1' AND content_type='Movie'), 2)
    """
).fetchone()
print(f"Show : Movie hours-per-title ratio = {ratio[0]}x")

print()
print("--- total rows in both fact tables ---")
a = cur.execute("SELECT COUNT(*) FROM fact_top10_weekly").fetchone()[0]
b = cur.execute("SELECT COUNT(*) FROM fact_engagement_half").fetchone()[0]
print(f"fact_top10_weekly={a:,}  fact_engagement_half={b:,}  total={a+b:,}")

print()
print("--- weekly Top 10 date span ---")
print(cur.execute("SELECT MIN(date_key), MAX(date_key) FROM fact_top10_weekly").fetchone())
print("distinct countries:", cur.execute("SELECT COUNT(*) FROM dim_region WHERE is_global=0").fetchone()[0])
