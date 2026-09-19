"""
Builds a small star schema (SQLite) from Netflix's public engagement datasets:
  - What We Watched engagement reports (biannual, real hours-viewed by title)
  - Weekly Top 10 by country / global (weekly rank + hours for global Top 10)

Output:
  - data/netflix_engagement.db   (SQLite database, dims + facts)
  - data/model/*.csv             (flat exports for Power BI "Get Data > Text/CSV")
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MODEL = ROOT / "data" / "model"
DB_PATH = ROOT / "data" / "netflix_engagement.db"

MODEL.mkdir(parents=True, exist_ok=True)

HALF_YEAR_FILES = [
    ("Netflix-What-We-Watched-2025Jan-Jun.xlsx", "2025-01-01", "2025-06-30", "2025H1"),
    ("Netflix-What-We-Watched-2025Jul-Dec.xlsx", "2025-07-01", "2025-12-31", "2025H2"),
    ("Netflix-What-We-Watched-2026Jan-Jun.xlsx", "2026-01-01", "2026-06-30", "2026H1"),
]


def disambiguate_title(show_title, season_title):
    """Top 10 files split a show's season into `season_title` (e.g. 'The
    Gentlemen: Season 2') while `show_title` stays generic ('The Gentlemen') -
    two concurrently-charting seasons of the same show would otherwise collide
    into one title. Prefer the fully-qualified season_title when present."""
    if season_title is not None and str(season_title).strip() not in ("N/A", "nan", ""):
        return str(season_title).strip()
    return str(show_title).strip()


def runtime_to_minutes(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if ":" not in s:
        return None
    h, m = s.split(":")
    try:
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def load_half_year_reports():
    """Parse the 3 biannual 'What We Watched' workbooks into one long dataframe."""
    frames = []
    for fname, start, end, label in HALF_YEAR_FILES:
        path = RAW / fname
        for sheet, content_type in (("Shows", "Show"), ("Movies", "Movie")):
            df = pd.read_excel(path, sheet_name=sheet, skiprows=5)
            df = df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")], errors="ignore")
            df = df.dropna(subset=["Title"])
            df["content_type"] = content_type
            df["period_label"] = label
            df["period_start"] = start
            df["period_end"] = end
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(
        columns={
            "Title": "title_name",
            "Available Globally?": "is_available_globally",
            "Release Date": "release_date",
            "Hours Viewed": "hours_viewed",
            "Runtime": "runtime_raw",
            "Views": "views",
        }
    )
    out["runtime_minutes"] = out["runtime_raw"].apply(runtime_to_minutes)
    out["title_name"] = out["title_name"].str.strip()
    return out[
        [
            "title_name",
            "content_type",
            "period_label",
            "period_start",
            "period_end",
            "is_available_globally",
            "release_date",
            "hours_viewed",
            "views",
            "runtime_minutes",
        ]
    ]


def load_global_top10():
    df = pd.read_csv(RAW / "all-weeks-global.tsv", sep="\t")
    df = df.rename(
        columns={
            "week": "week_start_date",
            "category": "category_raw",
            "weekly_rank": "weekly_rank",
            "show_title": "title_name",
            "season_title": "season_title",
            "weekly_hours_viewed": "hours_viewed",
            "runtime": "runtime_hours",
            "weekly_views": "views",
            "cumulative_weeks_in_top_10": "cumulative_weeks_in_top10",
        }
    )
    df["content_type"] = df["category_raw"].apply(lambda x: "Movie" if str(x).startswith("Films") else "Show")
    df["language"] = df["category_raw"].apply(lambda x: "Non-English" if "Non-English" in str(x) else "English")
    df["region_name"] = "Global"
    df["title_name"] = [disambiguate_title(t, s) for t, s in zip(df["title_name"], df["season_title"])]
    return df[
        [
            "week_start_date",
            "region_name",
            "title_name",
            "season_title",
            "content_type",
            "language",
            "weekly_rank",
            "hours_viewed",
            "views",
            "runtime_hours",
            "cumulative_weeks_in_top10",
        ]
    ]


def load_country_top10():
    df = pd.read_csv(RAW / "all-weeks-countries.tsv", sep="\t")
    df = df.rename(
        columns={
            "country_name": "region_name",
            "country_iso2": "iso2",
            "week": "week_start_date",
            "category": "content_type",
            "weekly_rank": "weekly_rank",
            "show_title": "title_name",
            "season_title": "season_title",
            "cumulative_weeks_in_top_10": "cumulative_weeks_in_top10",
        }
    )
    df["content_type"] = df["content_type"].map({"Films": "Movie", "TV": "Show"}).fillna(df["content_type"])
    df["title_name"] = [disambiguate_title(t, s) for t, s in zip(df["title_name"], df["season_title"])]
    df["hours_viewed"] = None
    df["views"] = None
    df["runtime_hours"] = None
    df["language"] = None
    return df[
        [
            "week_start_date",
            "region_name",
            "iso2",
            "title_name",
            "season_title",
            "content_type",
            "language",
            "weekly_rank",
            "hours_viewed",
            "views",
            "runtime_hours",
            "cumulative_weeks_in_top10",
        ]
    ]


def build_dim_date(all_dates):
    dates = pd.to_datetime(pd.Series(sorted(set(all_dates))))
    dim = pd.DataFrame({"full_date": dates})
    dim["date_key"] = dim["full_date"].dt.strftime("%Y-%m-%d")
    dim["year"] = dim["full_date"].dt.year
    dim["month"] = dim["full_date"].dt.month
    dim["month_name"] = dim["full_date"].dt.strftime("%B")
    dim["quarter"] = dim["full_date"].dt.quarter
    dim["half"] = dim["full_date"].dt.month.apply(lambda m: "H1" if m <= 6 else "H2")
    dim["half_label"] = dim["year"].astype(str) + dim["half"]
    dim["iso_week"] = dim["full_date"].dt.isocalendar().week
    dim["full_date"] = dim["date_key"]
    return dim[["date_key", "full_date", "year", "quarter", "half_label", "month", "month_name", "iso_week"]]


def main():
    print("Loading half-year engagement reports...")
    half = load_half_year_reports()
    print(f"  {len(half):,} title x half rows")

    print("Loading global weekly Top 10...")
    global_top10 = load_global_top10()
    print(f"  {len(global_top10):,} rows")

    print("Loading country weekly Top 10 (large file)...")
    country_top10 = load_country_top10()
    print(f"  {len(country_top10):,} rows")

    # ---------- dim_title ----------
    title_frames = pd.concat(
        [
            half[["title_name", "content_type"]],
            global_top10[["title_name", "content_type"]],
            country_top10[["title_name", "content_type"]],
        ],
        ignore_index=True,
    ).dropna(subset=["title_name"])
    # Natural key is (title_name, content_type): a handful of titles share a name
    # across different works of a different type (e.g. "The Gentlemen" is both a
    # 2019 film and a 2024 Netflix series) - keying on name alone would silently
    # merge them into one title and corrupt any rank-change / trend logic.
    dim_title = title_frames.drop_duplicates(subset=["title_name", "content_type"]).reset_index(drop=True)
    dim_title["title_id"] = dim_title.index + 1
    dim_title = dim_title[["title_id", "title_name", "content_type"]]

    # ---------- dim_region ----------
    region_names = sorted(set(country_top10["region_name"].dropna().unique()) | {"Global"})
    dim_region = pd.DataFrame({"region_name": region_names})
    iso_lookup = country_top10.drop_duplicates("region_name").set_index("region_name")["iso2"].to_dict()
    dim_region["iso2"] = dim_region["region_name"].map(iso_lookup)
    dim_region["is_global"] = dim_region["region_name"] == "Global"
    dim_region["region_id"] = dim_region.index + 1
    dim_region = dim_region[["region_id", "region_name", "iso2", "is_global"]]
    region_map = dict(zip(dim_region["region_name"], dim_region["region_id"]))

    # ---------- dim_date ----------
    all_dates = (
        list(global_top10["week_start_date"].unique())
        + list(country_top10["week_start_date"].unique())
        + [s for _, s, _, _ in HALF_YEAR_FILES]
    )
    dim_date = build_dim_date(all_dates)

    # ---------- fact_top10_weekly ----------
    global_top10["region_id"] = global_top10["region_name"].map(region_map)
    country_top10["region_id"] = country_top10["region_name"].map(region_map)

    fact_cols = [
        "week_start_date",
        "region_id",
        "title_name",
        "content_type",
        "language",
        "weekly_rank",
        "hours_viewed",
        "views",
        "cumulative_weeks_in_top10",
    ]
    fact_top10 = pd.concat([global_top10[fact_cols], country_top10[fact_cols]], ignore_index=True)
    fact_top10 = fact_top10.merge(dim_title, on=["title_name", "content_type"], how="left")
    fact_top10 = fact_top10.rename(columns={"week_start_date": "date_key"})
    fact_top10 = fact_top10[
        ["date_key", "title_id", "region_id", "content_type", "language", "weekly_rank", "hours_viewed", "views", "cumulative_weeks_in_top10"]
    ]

    # ---------- fact_engagement_half ----------
    half = half.merge(dim_title, on=["title_name", "content_type"], how="left")
    half = half.rename(columns={"period_start": "date_key"})
    fact_half = half[
        [
            "date_key",
            "title_id",
            "content_type",
            "period_label",
            "is_available_globally",
            "release_date",
            "hours_viewed",
            "views",
            "runtime_minutes",
        ]
    ]

    # ---------- write SQLite ----------
    print(f"Writing {DB_PATH} ...")
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    dim_date.to_sql("dim_date", conn, index=False)
    dim_title.to_sql("dim_title", conn, index=False)
    dim_region.to_sql("dim_region", conn, index=False)
    fact_top10.to_sql("fact_top10_weekly", conn, index=False)
    fact_half.to_sql("fact_engagement_half", conn, index=False)

    conn.execute("CREATE INDEX idx_fact_top10_date ON fact_top10_weekly(date_key)")
    conn.execute("CREATE INDEX idx_fact_top10_title ON fact_top10_weekly(title_id)")
    conn.execute("CREATE INDEX idx_fact_top10_region ON fact_top10_weekly(region_id)")
    conn.execute("CREATE INDEX idx_fact_half_title ON fact_engagement_half(title_id)")
    conn.commit()
    conn.close()

    # ---------- export flat CSVs for Power BI ----------
    print(f"Exporting CSVs to {MODEL} ...")
    dim_date.to_csv(MODEL / "dim_date.csv", index=False)
    dim_title.to_csv(MODEL / "dim_title.csv", index=False)
    dim_region.to_csv(MODEL / "dim_region.csv", index=False)
    fact_top10.to_csv(MODEL / "fact_top10_weekly.csv", index=False)
    fact_half.to_csv(MODEL / "fact_engagement_half.csv", index=False)

    print("Done.")
    print(f"  dim_date:            {len(dim_date):,} rows")
    print(f"  dim_title:           {len(dim_title):,} rows")
    print(f"  dim_region:          {len(dim_region):,} rows")
    print(f"  fact_top10_weekly:   {len(fact_top10):,} rows")
    print(f"  fact_engagement_half:{len(fact_half):,} rows")


if __name__ == "__main__":
    main()
