#!/usr/bin/env python3
"""Turn the per-person CSVs from the other prep scripts into one ShareGPT
dataset for Unsloth or LLaMA-Factory.

Rewritten for this repository: the 2025 run did this step by hand in a
notebook that no longer exists, so this is the same transformation written
down. Each CSV is `sender¦timestamp¦content` with sender 0 for you and 1 for
the other person. A silence longer than --gap-hours starts a new conversation,
consecutive messages from one sender become one turn joined by newlines, and
your turns are `gpt`, theirs `human`.

  python csv_to_sharegpt.py --name "Your Name" --out sharegpt.json person1.csv person2.csv
"""
import argparse, csv, json, os
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument("csvs", nargs="+")
ap.add_argument("--name", required=True, help="whose messages the model learns")
ap.add_argument("--gap-hours", type=float, default=3)
ap.add_argument("--out", default="sharegpt.json")
a = ap.parse_args()

def stamp(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return datetime.fromtimestamp(int(s) / 1000)

out = []
for path in a.csvs:
    other = os.path.splitext(os.path.basename(path))[0]
    rows = [r for r in csv.reader(open(path, encoding="utf-8"), delimiter="¦") if len(r) == 3 and r[0] in "01"]
    conv, last = [], None
    def flush():
        # A conversation must contain at least one of your turns to teach anything.
        if any(t["from"] == "gpt" for t in conv):
            if conv[0]["from"] == "gpt":
                conv.insert(0, {"from": "human", "value": "(you text first)"})
            out.append({"system": f"You are {a.name}, texting {other}.", "conversations": list(conv)})
    for sender, ts, text in rows:
        t = stamp(ts)
        if last and (t - last).total_seconds() > a.gap_hours * 3600:
            flush(); conv.clear()
        role = "gpt" if sender == "0" else "human"
        if conv and conv[-1]["from"] == role:
            conv[-1]["value"] += "\n" + text
        else:
            conv.append({"from": role, "value": text})
        last = t
    flush()
json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "conversations ->", a.out)
