"""
Fetch current YouTube view counts for the trailers in data/trailers/trailer_map.csv
into fact_trailer_engagement in the local SQLite build, then run sql/trailers.sql.

Why the counts are never committed
----------------------------------
YouTube's API policies let an app keep statistics for videos it doesn't own for
no longer than 30 days (Developer Policies III.E.4.d), and require showing the
most recent data available (III.E.4.f). So:

  - the counts live only in data/netflix_engagement.db, which is gitignored
  - every row carries fetched_at
  - every run deletes rows older than 30 days before adding new ones

What is committed is data/trailers/trailer_map.csv: which trailer belongs to
which title, chosen and checked by hand. Searching "<title> trailer" returns fan
re-uploads, reaction videos and trailers for other films, so every match was
reviewed before it went in, and the note column says why each one is there.

Needs YOUTUBE_API_KEY in .env (gitignored). One videos.list call covers every
trailer, which costs 1 unit of the 10,000-unit daily quota.

    python scripts/fetch_trailers.py
"""

import csv
import io
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data" / "trailers" / "trailer_map.csv"
DB = ROOT / "data" / "netflix_engagement.db"
SQL = ROOT / "sql" / "trailers.sql"
KEEP_DAYS = 30


def api_key() -> str:
    """Read the key without ever printing it, tolerating stray spaces or quotes."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "YOUTUBE_API_KEY" and value.strip():
                return value.strip().strip('"').strip("'")
    raise SystemExit("YOUTUBE_API_KEY is not set in .env")


def fetch(video_ids: list[str], key: str) -> dict[str, dict]:
    query = urllib.parse.urlencode({"part": "statistics,snippet", "id": ",".join(video_ids), "key": key})
    try:
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/videos?{query}", timeout=30) as r:
            items = json.load(r).get("items", [])
    except urllib.error.HTTPError as e:
        message = json.load(e).get("error", {}).get("message", "")
        raise SystemExit(f"YouTube answered {e.code}: {message}")
    return {v["id"]: v for v in items}


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"{DB} not found: run scripts/build_star_schema.py first")
    trailers = list(csv.DictReader(MAP.open(encoding="utf-8")))
    found = fetch([t["video_id"] for t in trailers], api_key())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = sqlite3.connect(DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fact_trailer_engagement (
               title_id     INTEGER REFERENCES dim_title(title_id),
               video_id     TEXT NOT NULL,
               view_count   INTEGER,
               like_count   INTEGER,
               published_at TEXT,
               fetched_at   TEXT NOT NULL
           )"""
    )
    removed = conn.execute(
        "DELETE FROM fact_trailer_engagement WHERE julianday(?) - julianday(fetched_at) > ?",
        (now, KEEP_DAYS),
    ).rowcount

    missing = []
    for t in trailers:
        v = found.get(t["video_id"])
        if not v:
            missing.append(t["title_name"])
            continue
        s = v["statistics"]
        conn.execute(
            "INSERT INTO fact_trailer_engagement VALUES (?, ?, ?, ?, ?, ?)",
            (
                int(t["title_id"]),
                t["video_id"],
                int(s.get("viewCount", 0)),
                int(s["likeCount"]) if "likeCount" in s else None,
                v["snippet"]["publishedAt"][:10],
                now,
            ),
        )
    conn.commit()

    print(f"fetched {len(found)} of {len(trailers)} trailers at {now}; removed {removed} rows older than {KEEP_DAYS} days")
    if missing:
        print("no longer on YouTube, check the map:", ", ".join(missing))

    cur = conn.execute(SQL.read_text(encoding="utf-8"))
    cols = [c[0] for c in cur.description]
    print("\n" + " | ".join(cols))
    for row in cur.fetchall():
        print(" | ".join("" if x is None else str(x) for x in row))
    conn.close()


if __name__ == "__main__":
    main()
