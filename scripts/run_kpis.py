import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

conn = sqlite3.connect("data/netflix_engagement.db")
cur = conn.cursor()
sql = open("sql/kpis.sql", encoding="utf-8").read()
statements = [s.strip() for s in sql.split(";") if s.strip()]

for i, stmt in enumerate(statements):
    lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
    if not lines:
        continue
    clean = "\n".join(lines)
    try:
        cur.execute(clean)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        print(f"=== STATEMENT {i} ===")
        print(cols)
        for r in rows[:20]:
            print(r)
        print()
    except Exception as e:
        print(f"STATEMENT {i} ERROR: {e}")
        print(clean[:200])
