#!/usr/bin/env python3
"""Build unified.db: every message from three archives in one table, with a
drop reason on rows that should not be trained on. Rebuilds from scratch each
run; the sources are never modified.

  python build_unified.py --textview messages.db --instagram <export>/messages \
      --discord <DiscordChatExporter JSON dir> --self-name "Your Name" --discord-self-id 1234

Every source is optional. TextView is the author's own SMS/RCS/iMessage
archive (a SQLite schema with participants, messages and reaction tables);
--instagram is the `messages` folder of an Instagram data download; --discord
is a folder of DiscordChatExporter JSON files.
"""
import sqlite3, os, json, glob, re, datetime, sys, argparse

ap = argparse.ArgumentParser()
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap.add_argument("--out", default=f"{HERE}/unified.db")
ap.add_argument("--textview")
ap.add_argument("--instagram")
ap.add_argument("--discord")
ap.add_argument("--self-name", help="your display name in the Instagram export")
ap.add_argument("--discord-self-id", help="your Discord user id")
ARGS = ap.parse_args()
OUT, TEXTVIEW, INSTAGRAM, DISCORD = ARGS.out, ARGS.textview, ARGS.instagram, ARGS.discord
IG_SELF, DISCORD_SELF = ARGS.self_name, ARGS.discord_self_id

URL = re.compile(r"https?://\S+")
TAPBACK = re.compile(
    r"^\s*[​-‏‪-‮⁠-⁯]*"
    r"(Liked|Loved|Laughed at|Emphasized|Disliked|Questioned|Removed an? \w+ from|Reacted .{1,12} to|.{1,12} to) “",
    re.S)
IG_REACT = re.compile(r"^(Liked a message|Reacted .{1,12} to your message ?|.* (liked|reacted .* to) (a|your) message)$")
DISCORD_EMOJI = re.compile(r"<a?:(\w+):\d+>")

def clean(text):
    """Returns (text, kind). URLs become <link> so the model learns that a link
    was sent without memorising the address."""
    if text is None:
        return "", "empty"
    t = text.replace("￼", "").replace("\r\n", "\n").strip()
    if not t:
        return "", "empty"
    t2 = URL.sub("<link>", t)
    if t2 == "<link>":
        return t2, "link"
    return t2, "text"

def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    out = sqlite3.connect(OUT)
    out.executescript("""
    create table messages(
      uid integer primary key, source text, thread text, sender text, is_me int,
      ts_ms int, text text, kind text, drop_reason text, src_id text, reply_to text);
    create table threads(thread text primary key, source text, title text, is_group int,
      n int, n_me int, first_ms int, last_ms int, drop_reason text);
    create table identities(source text, key text, name text, n int, primary key(source,key));
    """)
    rows = []
    idn = {}
    titles = {}

    # ---- TextView
    tv = sqlite3.connect(f"file:{TEXTVIEW}?mode=ro", uri=True) if TEXTVIEW else sqlite3.connect(":memory:")
    if not TEXTVIEW:  # an empty schema, so the TextView pass below finds nothing
        tv.executescript("create table participant_names(participant_id,name,occurrence_count); create table participants(id,display_address,canonical_address,is_self); create table message_participants(message_id,participant_id,role); create table reaction_events(reaction_message_id); create table sticker_events(sticker_message_id); create table message_parts(message_id,content_type); create table message_replies(message_id,target_message_id); create table messages(id,timestamp_ms,direction,transport,body,status);")
    names = {}
    for pid, name, cnt in tv.execute("select participant_id,name,occurrence_count from participant_names order by occurrence_count"):
        names[pid] = name
    addr = dict(tv.execute("select id, display_address from participants"))
    canon = dict(tv.execute("select id, canonical_address from participants"))
    selfs = {r[0] for r in tv.execute("select id from participants where is_self=1")}
    parts, frm = {}, {}
    for mid, pid, role in tv.execute("select message_id, participant_id, role from message_participants"):
        if pid in selfs:
            continue
        parts.setdefault(mid, set()).add(pid)
        if role == "from":
            frm[mid] = pid
    reaction_ids = {r[0] for r in tv.execute("select reaction_message_id from reaction_events")}
    sticker_ids = {r[0] for r in tv.execute("select sticker_message_id from sticker_events")}
    has_parts = {r[0] for r in tv.execute("select distinct message_id from message_parts where content_type not like 'text/%' and content_type not like 'application/smil%'")}
    replies = dict(tv.execute("select message_id, target_message_id from message_replies where target_message_id is not null"))
    for mid, ts, direction, transport, body, status in tv.execute(
            "select id,timestamp_ms,direction,transport,body,status from messages order by timestamp_ms,id"):
        ps = parts.get(mid)
        if not ps or direction not in ("incoming", "outgoing"):
            continue
        thread = "tv:" + ",".join(str(p) for p in sorted(ps))
        is_me = int(direction == "outgoing")
        sender = "me" if is_me else f"tv:{frm.get(mid, min(ps))}"
        text, kind = clean(body)
        drop = None
        if status in ("hidden", "announcement", "app"):
            drop = status
        elif mid in reaction_ids or TAPBACK.match(text):
            drop = "reaction"
        elif mid in sticker_ids:
            drop = "sticker"
        elif kind == "empty":
            if mid in has_parts:
                text, kind = "<media>", "media"
            else:
                drop = "empty"
        elif text.startswith("Edited to “"):
            drop = "edit-fallback"
        platform = "imessage" if transport == "imessage" else "sms"
        rows.append(("textview", thread, sender, is_me, ts, text, kind, drop, str(mid),
                     str(replies[mid]) if mid in replies else None, platform))
    for pid in addr:
        if pid not in selfs:
            idn[("textview", f"tv:{pid}")] = names.get(pid) or addr[pid]
    for r in rows:
        if r[1] not in titles:
            ids = [int(x) for x in r[1][3:].split(",")]
            titles[r[1]] = (", ".join(names.get(i) or addr.get(i, "?") for i in ids), int(len(ids) > 1))
    n_tv = len(rows)

    # ---- Instagram. The export stores UTF-8 bytes as Latin-1 code points.
    fix = lambda s: s.encode("latin1").decode("utf8", "replace") if s else s
    for box in ("inbox", "message_requests"):
        for tdir in (sorted(glob.glob(f"{glob.escape(INSTAGRAM)}/{box}/*")) if INSTAGRAM else []):
            msgs, meta = [], None
            for f in glob.glob(glob.escape(tdir) + "/message_*.json"):
                j = json.load(open(f))
                meta = meta or j
                msgs += j["messages"]
            if not meta:
                continue
            thread = "ig:" + meta["thread_path"]
            others = [fix(p["name"]) for p in meta["participants"] if fix(p["name"]) != IG_SELF]
            titles[thread] = (fix(meta.get("title")) or ", ".join(others), int(len(others) > 1))
            for i, m in enumerate(sorted(msgs, key=lambda m: m["timestamp_ms"])):
                who = fix(m.get("sender_name")) or "?"
                is_me = int(who == IG_SELF)
                sender = "me" if is_me else f"ig:{who}"
                if not is_me:
                    idn[("instagram", sender)] = who
                text, kind = clean(fix(m.get("content")))
                drop = None
                media = any(k in m for k in ("photos", "videos", "audio_files", "gifs", "sticker", "share"))
                if m.get("is_unsent"):
                    drop = "unsent"
                elif "call_duration" in m:
                    drop = "call"
                elif kind != "empty" and IG_REACT.match(text):
                    drop = "reaction"
                elif media and (kind == "empty" or "sent an attachment" in text or "shared a story" in text):
                    text, kind = "<media>", "media"
                elif kind == "empty":
                    drop = "empty"
                rows.append(("instagram", thread, sender, is_me, m["timestamp_ms"], text, kind, drop,
                             f"{meta['thread_path']}#{i}", None, "instagram"))
    n_ig = len(rows) - n_tv

    # ---- Discord (DiscordChatExporter JSON)
    for f in (sorted(glob.glob(glob.escape(DISCORD) + "/*.json")) if DISCORD else []):
        j = json.load(open(f, encoding="utf-8-sig"))
        ch = j["channel"]
        thread = "dc:" + ch["id"]
        authors = set()
        for m in j["messages"]:
            a = m["author"]
            is_me = int(a["id"] == DISCORD_SELF)
            sender = "me" if is_me else f"dc:{a['id']}"
            if not is_me:
                idn[("discord", sender)] = a.get("nickname") or a["name"]
                idn[("discord_user", sender)] = a["name"]
                authors.add(a["id"])
            ts = int(datetime.datetime.fromisoformat(m["timestamp"]).timestamp() * 1000)
            text, kind = clean(DISCORD_EMOJI.sub(r":\1:", m.get("content") or ""))
            drop = None
            if m["type"] not in ("Default", "Reply"):
                drop = "system"
            elif a.get("isBot"):
                drop = "bot"
            elif kind == "empty":
                if m.get("attachments") or m.get("stickers") or m.get("embeds"):
                    text, kind = "<media>", "media"
                else:
                    drop = "empty"
            ref = (m.get("reference") or {}).get("messageId")
            rows.append(("discord", thread, sender, is_me, ts, text, kind, drop, m["id"], ref, "discord"))
        titles[thread] = (ch["name"], int(ch["type"] == "DirectGroupTextChat"))
    n_dc = len(rows) - n_tv - n_ig

    out.execute("alter table messages add column platform text")
    out.executemany("insert into messages(source,thread,sender,is_me,ts_ms,text,kind,drop_reason,src_id,reply_to,platform) values(?,?,?,?,?,?,?,?,?,?,?)", rows)
    out.executemany("insert or replace into identities values(?,?,?,0)", [(s, k, n) for (s, k), n in idn.items()])
    out.execute("update identities set n=(select count(*) from messages m where m.sender=identities.key and m.drop_reason is null)")
    out.execute("""insert into threads select thread, min(source), null, 0, sum(drop_reason is null),
                   sum(drop_reason is null and is_me), min(ts_ms), max(ts_ms), null from messages group by thread""")
    out.executemany("update threads set title=?, is_group=? where thread=?", [(t, g, k) for k, (t, g) in titles.items()])
    # A thread he never wrote in teaches nothing about him; most are automated senders.
    out.execute("update threads set drop_reason='no outgoing' where n_me=0")
    out.execute("update threads set drop_reason='tiny' where drop_reason is null and n<6")
    out.execute("update messages set drop_reason='thread:'||(select drop_reason from threads t where t.thread=messages.thread) where drop_reason is null and thread in (select thread from threads where drop_reason is not null)")
    out.executescript("create index m_thread on messages(thread, ts_ms); create index m_sender on messages(sender);")
    out.commit()
    print("rows", n_tv, n_ig, n_dc)
    for r in out.execute("select source, sum(drop_reason is null), sum(drop_reason is null and is_me), sum(case when drop_reason is null and is_me then length(text) end) from messages group by 1"):
        print(r)
    for r in out.execute("select source, drop_reason, count(*) from messages where drop_reason is not null group by 1,2 order by 1,3 desc"):
        print("  dropped", r)
    print("threads kept", out.execute("select source,count(*),sum(is_group) from threads where drop_reason is null group by 1").fetchall())

if __name__ == "__main__":
    main()
