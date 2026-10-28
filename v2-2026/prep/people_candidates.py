#!/usr/bin/env python3
"""Write people.csv: one row per one-to-one thread with 100+ kept messages,
grouped into suggested people by name. The owner corrects the grouping and
fills in `relationship`; export.py reads the result. Never overwrites a
people.csv that already exists."""
import sqlite3, csv, re, unicodedata, os, sys, datetime, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{HERE}/people.csv"
if os.path.exists(OUT) and "--force" not in sys.argv:
    sys.exit("people.csv exists; pass --force to regenerate")

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s).split()

u = sqlite3.connect(f"{HERE}/unified.db")
rows = u.execute("""select source, thread, title, n, n_me, first_ms, last_ms from threads
                    where drop_reason is null and is_group=0 and n>=100 order by n desc""").fetchall()
groups = []          # each: {"tokens": set of full-name token tuples, "first": str, "rows": [...]}
for r in rows:
    toks = norm(r[2])
    hit, basis = None, "none"
    if toks:
        for g in groups:
            if tuple(toks) in g["full"]:
                hit, basis = g, "same name"; break
        if not hit:
            for g in groups:
                if toks[0] == g["first"] and len(toks[0]) > 2:
                    hit, basis = g, "first name only, check"; break
    if not hit:
        hit = {"full": set(), "first": toks[0] if toks else "", "rows": [], "name": r[2]}
        groups.append(hit)
        basis = "new"
    hit["full"].add(tuple(toks))
    hit["rows"].append((r, basis))
groups.sort(key=lambda g: -sum(r[0][3] for r in g["rows"]))
y = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).year
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["person", "relationship", "source", "title", "messages", "yours", "years", "match", "thread"])
    for g in groups:
        for r, basis in g["rows"]:
            w.writerow([g["name"], "", r[0], r[2], r[3], r[4], f"{y(r[5])}-{y(r[6])}", basis, r[1]])
tot = sum(r[3] for r in rows)
print(len(rows), "threads,", len(groups), "suggested people,", tot, "messages")
cum = 0
for i, g in enumerate(groups[:60], 1):
    n = sum(r[0][3] for r in g["rows"]); cum += n
    print(i, g["name"], n, "|".join(f"{r[0][0][:2]}:{r[0][2]}" for r in g["rows"]), f"cum {cum/tot:.0%}")
