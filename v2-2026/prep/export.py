#!/usr/bin/env python3
"""Turn unified.db into training conversations.

Each line of the output is one conversation: a system line saying who Ben is
talking to, where and when, then alternating turns. The other side is `user`,
Ben is `assistant`, so a trainer that masks loss to assistant turns trains on
his words only. Consecutive messages from one sender are one turn, joined by
newlines: a newline is a new bubble.

  --gap-hours   silence that ends a conversation (default 3)
  --max-chars   longest conversation before it is cut into pieces (default 6000)
"""
import sqlite3, json, csv, os, argparse, datetime, random, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--gap-hours", type=float, default=3)
ap.add_argument("--max-chars", type=int, default=6000)
ap.add_argument("--eval-frac", type=float, default=0.03)
ap.add_argument("--out", default=f"{HERE}/dataset")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

people = {}
if os.path.exists(f"{HERE}/people.csv"):
    for r in csv.DictReader(open(f"{HERE}/people.csv")):
        people[r["thread"]] = (r["person"].strip(), r["relationship"].strip())

u = sqlite3.connect(f"{HERE}/unified.db")
names = {k: n for _, k, n in u.execute("select source,key,name from identities where source!='discord_user'")}
PLATFORM = {"sms": "text message", "imessage": "iMessage", "instagram": "Instagram", "discord": "Discord"}
FIRST = "(Ben texts first)"

def system_line(thread, title, is_group, platform, ts):
    when = datetime.datetime.fromtimestamp(ts / 1000).strftime("%B %Y")
    if is_group:
        who = f"a group chat ({title})"
    else:
        person, rel = people.get(thread, (title, ""))
        who = f"{person} ({rel})" if rel else person
    return f"Ben is messaging {who} on {PLATFORM[platform]}, {when}."

def turns_of(msgs, is_group):
    """msgs: (sender, is_me, ts, text). Merge same-sender runs; merge every
    non-Ben run into one user turn, with speaker names in a group."""
    out = []
    for sender, is_me, ts, text in msgs:
        role = "assistant" if is_me else "user"
        line = text if (is_me or not is_group) else None
        if out and out[-1]["role"] == role and (is_me or not is_group or out[-1]["who"] == sender):
            out[-1]["content"] += "\n" + text
        elif out and out[-1]["role"] == role:
            out[-1]["content"] += f"\n{names.get(sender, '?')}: {text}"
            out[-1]["who"] = sender
        else:
            out.append({"role": role, "who": sender,
                        "content": text if line is not None else f"{names.get(sender, '?')}: {text}"})
    for t in out:
        t.pop("who")
    return out

def pieces(turns, cap):
    cur, size = [], 0
    for t in turns:
        if cur and size + len(t["content"]) > cap and t["role"] == "user":
            yield cur
            cur, size = [], 0
        cur.append(t); size += len(t["content"])
    if cur:
        yield cur

convs = []
gap = a.gap_hours * 3600_000
for thread, title, is_group in u.execute("select thread,title,is_group from threads where drop_reason is null"):
    block = []
    def flush():
        if not block:
            return
        for p in pieces(turns_of([(s, m, t, x) for s, m, t, x, _ in block], is_group), a.max_chars):
            if not any(t["role"] == "assistant" for t in p):
                continue
            if p[0]["role"] == "assistant":
                p = [{"role": "user", "content": FIRST}] + p
            ts, platform = block[0][2], block[0][4]
            convs.append({"messages": [{"role": "system", "content": system_line(thread, title, is_group, platform, ts)}] + p,
                          "meta": {"thread": thread, "year": datetime.datetime.fromtimestamp(ts / 1000).year,
                                   "platform": platform, "group": bool(is_group), "start_ms": ts}})
    last = None
    for row in u.execute("select sender,is_me,ts_ms,text,platform from messages where thread=? and drop_reason is null order by ts_ms,uid", (thread,)):
        if last is not None and row[2] - last > gap:
            flush(); block = []
        block.append(row); last = row[2]
    flush()

random.seed(20261007)
recent = [c for c in convs if c["meta"]["year"] >= 2025 and len(c["messages"]) >= 5]
held = set(id(c) for c in random.sample(recent, int(len(recent) * a.eval_frac)))
stats = collections.defaultdict(lambda: [0, 0, 0])
with open(f"{a.out}/train.jsonl", "w") as tr, open(f"{a.out}/eval.jsonl", "w") as ev:
    for c in convs:
        (ev if id(c) in held else tr).write(json.dumps(c, ensure_ascii=False) + "\n")
        s = stats[("eval" if id(c) in held else "train", c["meta"]["year"])]
        s[0] += 1
        s[1] += sum(len(m["content"]) for m in c["messages"])
        s[2] += sum(len(m["content"]) for m in c["messages"] if m["role"] == "assistant")
print("split year  convs  chars_all  chars_ben  ~tokens_all (chars/4)")
tot = [0, 0, 0]
for k in sorted(stats):
    s = stats[k]; print(*k, s[0], s[1], s[2], s[1] // 4)
    if k[0] == "train":
        tot = [x + y for x, y in zip(tot, s)]
print("train total", tot, "~tokens", tot[1] // 4, "of which Ben", tot[2] // 4)
