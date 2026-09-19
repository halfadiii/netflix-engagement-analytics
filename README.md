# Streaming Engagement Analytics — a mini Disney+/Hulu engagement dashboard, built on Netflix's public data

A self-directed practice project built for a Data Analyst, Engagement Analytics interview: decompose
streaming engagement into content, time, and regional drivers using **real, official, publicly
released data** — no synthetic numbers anywhere in this repo.

## 1. The questions this dashboard answers

Framed directly in the language of the role (measurement of engagement trends and drivers across
content, subscriber, and product dimensions):

1. **What's driving engagement hours?** Which handful of titles account for a disproportionate share of viewing, and is growth coming from hit titles or from a growing long tail?
2. **Which content types perform best?** Shows vs. Movies, English vs. Non-English — where does an hour of production investment earn the most engagement?
3. **How does engagement trend over time?** Half-over-half and week-over-week, and is the trend accelerating or decelerating?
4. **Where is engagement concentrated regionally?** Which markets watch the same global hits, and which sustain engagement with a smaller set of titles for longer?
5. **What actually moves the needle week to week?** Which titles posted the biggest rank swings, and what caused it (e.g. a new season premiere)?

## 2. Data

All data is Netflix's own official public releases — no scraping of unofficial mirrors, no synthetic
rows.

| Source | Grain | What it adds |
|---|---|---|
| [What We Watched: A Netflix Engagement Report](https://about.netflix.com/en/news/what-we-watched-a-netflix-engagement-report) (3 most recent releases: 2025H1, 2025H2, 2026H1) | title x half-year, Global only | Real **hours viewed** for ~99% of all platform viewing — ~16-17k titles per half |
| [Netflix Top 10 — Global, weekly](https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv) | title x week, Global | Weekly hours/views/rank for the top 10 in each of 4 categories (Films/TV x English/Non-English), back to 2021 |
| [Netflix Top 10 — by country, weekly](https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv) | title x week x country | Weekly rank in 94 countries, back to 2021 (rank only — Netflix does not publish country-level hours) |

`scripts/fetch_data.sh` re-downloads all three (Netflix requires a real browser User-Agent header or
it 403s). TMDB genre enrichment was scoped out for v1 — see Limitations.

## 3. Method — star schema (fact constellation)

Two source datasets have genuinely different grains (weekly Top 10 vs. biannual full-catalog hours),
so this is modeled as a **fact constellation**: two fact tables sharing three conformed dimensions.
Same pattern as a classic star schema, just with two facts instead of one because the grains don't
honestly reconcile into a single table without throwing away information.

```
                dim_date ── date_key
                    │
        ┌───────────┴───────────┐
fact_top10_weekly       fact_engagement_half
  title_id, region_id     title_id
  weekly_rank              hours_viewed, views, runtime
  hours_viewed (Global     period_label ('2025H1'...)
    rows only), views
    │
dim_title (title_id)    dim_region (region_id)
```

Built with `scripts/build_star_schema.py` (pandas): parses the 3 xlsx workbooks + 2 TSVs, builds
`dim_date` / `dim_title` / `dim_region`, and writes both a SQLite database
(`data/netflix_engagement.db`) and flat CSVs (`data/model/*.csv`) for Power BI's Text/CSV connector.

Run it:
```bash
bash scripts/fetch_data.sh
pip install pandas openpyxl
python scripts/build_star_schema.py
```

### A real data-quality issue this surfaced (and why it matters)

The weekly Top 10 files store a show's season in a separate `season_title` column
(`show_title` stays generic, e.g. `"The Gentlemen"`, while `season_title` says
`"The Gentlemen: Season 2"`). Keying `dim_title` on `show_title` alone silently merged two
different chart entries (Season 1 and Season 2 of the same show) into one row, which then
corrupted a week-over-week rank-change calculation — every "biggest mover" came back as a
duplicate artifact, not a real signal. Fixed by keying on `season_title` when present. This
is exactly the kind of entity-resolution issue that shows up constantly in real engagement
data, and it's why `scripts/build_star_schema.py` has a `disambiguate_title()` function with
a comment explaining the fix rather than a silent `.drop_duplicates()`.

## 4. SQL layer

`sql/schema.sql` — DDL for the model above.
`sql/kpis.sql` — the KPI queries, written against SQLite, using window functions throughout:

- **Top-line KPIs**: total hours, titles tracked, avg hours/title per half
- **What's driving hours**: `RANK() OVER (PARTITION BY period ...)` + a running `SUM() OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` for cumulative concentration (what % of hours the top 10 titles account for)
- **Content-type breakdown**: share of hours by Show/Movie and English/Non-English
- **Trend over time**: half-over-half growth via `LAG() OVER (ORDER BY period_label)`; a weekly trend with a trailing-4-week moving average
- **Regional concentration**: since country data has no hours, two real proxies — average weeks a title "sticks" in a country's Top 10, and % of weeks a country's #1 matches the Global #1 (built via a self-join, not a window function, since it compares two different partitions of the same table)
- **Top/bottom movers**: `LAG() OVER (PARTITION BY region, title ORDER BY date)` for rank one week ago, filtered to consecutive weeks only

Run them: `python scripts/run_kpis.py` (dumps every query's result set).

**A second real bug this caught**: the movers query originally filtered to the latest week
*before* computing `LAG()`. Since a `WHERE` clause is applied before the window function is
evaluated, that left exactly one row per `(region, title)` partition, so `LAG()` returned
`NULL` for every single row and the query silently produced zero movers. Window functions
need the full history in scope — filter to the date you care about only in the outer query,
after the window has already run. Left as a comment in `sql/kpis.sql` because it's an easy
mistake to repeat.

## 5. Findings (validated against the actual data — not illustrative)

**Growth is coming from breadth, not depth.** Total hours grew from 95.19B (2025H1) → 96.21B
(2025H2, +1.1%) → 97.66B (2026H1, +1.5%) — accelerating. But titles tracked grew faster (16,177 →
17,371, +7.4% YoY) while average hours *per title* actually fell (5.88M → 5.62M). The platform is
growing by adding more titles that each individually earn less, not by making existing hits bigger.

**Shows earn ~3x what Movies earn per title, and the gap is widening.** In 2026H1, Shows are 47%
of catalog volume but 76.1% of hours (up from 74.7% in 2025H1); Movies grew in title count
(8,674 → 9,179) while *shrinking* in absolute hours (24.06B → 23.31B). Each incremental movie is
diluting the movie category's average rather than adding to it — a real content-portfolio signal
about where investment is and isn't converting to engagement.

**Non-English content is charting more often but earning much less per chart appearance.**
Non-English movies actually out-chart English movies in the Global Top 10 by distinct-title count
(1,129 vs 1,086), yet English movies earned more than double the hours (39.0B vs 18.0B). Breadth
of international content isn't yet translating into hours parity with English-language content.

**Regional engagement concentrates differently than volume would suggest.** Since Netflix doesn't
publish country-level hours, "concentration" here means behavior, not size: Ukraine, Bolivia, and
Pakistan sustain the same title in their Top 10 the longest (5.7-5.8 weeks average), while
Trinidad and Tobago, Martinique, and Guadeloupe churn through titles fastest (2.2-2.3 weeks) of
the 94 markets studied — a >2.5x spread in how long a hit holds a market's attention. Separately,
Canada and a cluster of smaller European markets track the Global #1 movie most closely (75-79%
of weeks) — and Canada is *also* one of the fastest-churning markets (2.46 weeks), a genuinely
different finding from stickiness: Canada watches what's globally trending right now and moves on
quickly, rather than settling into a smaller rotation of favorites. Conflating "watches what's
globally popular" with "watches media intensely" would be a real analytical mistake here.

**A season premiere revives the entire back catalog, simultaneously, worldwide.** In the week
"The Gentlemen: Season 2" launched (debuting #1 globally with 73.4M hours, charting in 90 of 94
markets), "Season 1" — dormant on the weekly charts since mid-2024 — re-entered the Top 10 in **85
of 94 markets**: climbing in 53 of them (by up to 8 rank places) and re-entering from outside the
chart entirely in 29 more, all in the same week. This is a directly actionable "content driver"
finding: a new-season launch's engagement lift is not confined to the new season, and measuring
the premiere alone undercounts what the release actually earned.

## 6. Power BI build

I can't operate Power BI Desktop directly, so here's the concrete build path against the CSVs
already sitting in `data/model/`:

1. **Get Data > Text/CSV**, import all 5 files in `data/model/` (`dim_date`, `dim_title`,
   `dim_region`, `fact_top10_weekly`, `fact_engagement_half`).
2. **Model view** — create relationships:
   - `dim_date[date_key]` (1) → `fact_top10_weekly[date_key]` (*) and → `fact_engagement_half[date_key]` (*)
   - `dim_title[title_id]` (1) → `fact_top10_weekly[title_id]` (*) and → `fact_engagement_half[title_id]` (*)
   - `dim_region[region_id]` (1) → `fact_top10_weekly[region_id]` (*)
   - Mark `dim_date` as the official **Date table** (Model view > right-click `dim_date` > "Mark as date table", using `full_date`).
3. **Measures** (New Measure), mirroring `sql/kpis.sql`:
   ```dax
   Total Hours (B) = SUM(fact_engagement_half[hours_viewed]) / 1000000000
   Titles Tracked = DISTINCTCOUNT(fact_engagement_half[title_id])
   Avg Hours per Title (M) = AVERAGE(fact_engagement_half[hours_viewed]) / 1000000
   Half over Half % =
       VAR CurrentHours = [Total Hours (B)]
       VAR PriorHours = CALCULATE([Total Hours (B)], PREVIOUSMONTH(dim_date[full_date]))
       RETURN DIVIDE(CurrentHours - PriorHours, PriorHours)
   Pct of Hours by Content Type =
       DIVIDE([Total Hours (B)], CALCULATE([Total Hours (B)], ALL(dim_title[content_type])))
   ```
   (`Half over Half %` needs `dim_date` filtered to one row per half — easiest is to build it off
   `dim_date[half_label]` with a plain period-over-period table visual rather than time
   intelligence, since there are only 3 periods.)
4. **Visuals**:
   - KPI card row: Total Hours, Titles Tracked, Avg Hours/Title, distinct region count
   - Line chart: weekly Global hours (`fact_top10_weekly` filtered to `region = Global`), with a
     4-week moving average measure
   - Stacked bar: hours by `content_type` per `period_label`
   - Table/map: `dim_region` x "avg weeks sticking in Top 10" (build this measure with
     `AVERAGEX` over `fact_top10_weekly[cumulative_weeks_in_top10]`, filtered to `is_global = 0`)
   - Slicers: `period_label` / date range, `region_name`, `content_type`
5. **Publish** to Power BI Service (or export static screenshots into this repo's `/screenshots`
   folder) and link it from the Projects section of your resume.

## 7. Limitations (worth saying out loud in the interview)

- **No genre tags.** TMDB enrichment was scoped out of v1 — "content type" here means
  Show/Movie/English/Non-English, not genre. A real follow-up would join `dim_title` to TMDB by
  fuzzy title match and handle the inevitable mismatches.
- **Country-level hours don't exist** in Netflix's public data — only rank. Every "regional
  engagement" claim here is a stated behavioral proxy (stickiness, global-alignment), not raw
  volume, and is labeled as such rather than presented as if it were hours.
- **Title matching across the two source files is approximate.** The half-year report already
  spells out seasons in the title string (`"Stranger Things 5"`); the weekly Top 10 files split it
  across `show_title`/`season_title`. They won't always line up as the exact same string, so a
  title's Top-10 weekly history and its half-year hours total are not guaranteed to be perfectly
  joined without additional fuzzy matching.
- **Netflix's own report has an "Other Shows"/"Other Movies" aggregate bucket** for long-tail
  titles below its reporting threshold — visible in the 2025H2 top-10-by-hours list. It's real
  Netflix methodology, not a bug in this pipeline, but it means "top title" rankings undercount
  how much of the tail actually exists.

## 8. The 60-second pitch

"I built a mini version of the engagement-analytics problem this role solves for Disney+/Hulu,
using Netflix's own public engagement disclosures — three half-years of full-catalog hours-viewed
data plus five years of weekly Top-10-by-country rank data. I modeled it as a small fact
constellation in SQLite, wrote the KPI layer in SQL with window functions for ranking and
trend logic, and found that Netflix's recent hours growth is coming from a widening content
catalog rather than bigger hits — average hours per title is actually declining even as total
hours grow — and that a new season's premiere measurably revives engagement with its own back
catalog, pulling its first season back into the Top 10 in 85 of 94 markets in a single week. Along the way I hit and fixed two real
data-quality bugs: a title-collision issue that silently merged two different show seasons, and
a window-function ordering mistake that made a 'biggest movers' query return nothing. I'd want to
bring that same instinct — validate the pipeline against known official totals, don't trust the
first result of a window function — to the content, subscriber, and product engagement questions
this team owns."

## 9. Trailer views against engagement (YouTube)

Does a trailer that draws a big audience on YouTube go with a title that draws
a big audience on Netflix? A small, deliberately careful test over **20 titles
from 2026H1**: 10 series and 10 films, each released and first charting in the
same half-year so their trailers have had a similar time to gather views, and
spread from the biggest hit (Bridgerton: Season 4, 889.8M hours) to titles that
spent a single week at the bottom of the Top 10.

**The matching was done by hand.** Searching "<title> trailer" returns fan
re-uploads, reviews and trailers for other films: the first match for *This is
I* was a different film's teaser, and *Eat Pray Bark* only had a German-language
clip. Every trailer in `data/trailers/trailer_map.csv` was checked against its
title, taken from the official Netflix channel for the title's home market, and
carries a note saying why it is there. Two titles were replaced because no
real trailer existed.

**The view counts are not in this repository.** YouTube's API policies let an
app keep statistics for videos it doesn't own for no more than 30 days
(Developer Policies III.E.4.d) and require showing current data (III.E.4.f).
So `scripts/fetch_trailers.py` writes them only to the gitignored SQLite build,
stamps every row with `fetched_at`, and deletes rows older than 30 days on every
run. The live dashboard fetches them fresh, at most once a day.

```bash
# needs YOUTUBE_API_KEY in .env (gitignored)
python scripts/fetch_trailers.py     # 1 API unit; fills fact_trailer_engagement, runs sql/trailers.sql
```

`sql/trailers.sql` sets each title's trailer views beside its hours viewed,
peak global rank and weeks in the global Top 10, ranked **within** series and
within films. Film trailers draw far more views than series trailers at similar
viewing levels, so ranking them together would mostly measure that split.

**What it can't tell you.** Twenty titles is enough to see whether the two
roughly move together, not to put a number on it. View counts are cumulative to
the day they were fetched, and a hit sends people back to its trailer, so the
arrow can point either way. No correlation coefficient is published for that
reason, and because YouTube's policies (III.E.4.h) rule out building new
metrics from its data.

## Repo structure

```
data/raw/          source files (fetch with scripts/fetch_data.sh)
data/model/        flat CSVs for Power BI's Text/CSV connector
data/netflix_engagement.db   SQLite build of the star schema (regenerate with the script below)
scripts/fetch_data.sh          downloads the 3 raw source datasets
scripts/build_star_schema.py   ETL -> dims/facts -> SQLite + CSVs
scripts/run_kpis.py            runs sql/kpis.sql and prints every result set
sql/schema.sql      DDL for the star schema
sql/kpis.sql        the KPI / analysis queries (window functions)
sql/trailers.sql    trailer views beside hours and chart performance
scripts/fetch_trailers.py      current YouTube counts -> local DB only (30-day limit)
data/trailers/trailer_map.csv  hand-checked trailer for each of the 20 titles
```
