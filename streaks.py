#!/usr/bin/env python3
"""Streaks Trainer: streak-based mastery practice for any multiple-choice subject.

The method (see METHOD.md):
  1. Pick one section, or one topic inside it.
  2. Answer easy questions until you get N in a row, then medium, then hard.
  3. A miss before the target sends the counter back to 0. So does a right answer you guessed.
  4. Untimed at first. Speed is a later, separate step: optional speed stages bring the
     average time per question down (4:00 -> 3:00 -> 2:30 -> 2:00).
  5. Every break gets a written note: what broke it, and what you will do differently.
     The next question is not served until that note exists.

Sections, topics and difficulty tiers come from taxonomy.json and the item bank; nothing
about a particular subject is built in. A question is never served twice.

Commands:
  serve [--port 8791] [--open]   run the app at http://127.0.0.1:PORT
  status                          ladders and bank in the terminal
  report                          per-ladder numbers and break patterns (read-only)

Load questions with import_items.py (CSV or JSON; see README.md and docs/ITEM-FORMAT.md).
Python 3.9+ standard library only.
"""
import argparse, hashlib, json, os, random, re, sqlite3, webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("STREAKS_DB", os.path.join(HERE, "streaks.db"))
UI = os.path.join(HERE, "streaks_ui.html")
TAXONOMY = os.environ.get("STREAKS_TAXONOMY", os.path.join(HERE, "taxonomy.json"))
PORT = 8791

TIERS = ("Easy", "Medium", "Hard")

# Streak targets per tier (easy, medium, hard). "custom" accepts any numbers from 1 to 50,
# which is also how a short demo ladder is made.
GOALS = {
    "modest": {"label": "10 · 10 · 5", "targets": {"Easy": 10, "Medium": 10, "Hard": 5}},
    "lower":  {"label": "15 · 10 · 5", "targets": {"Easy": 15, "Medium": 10, "Hard": 5}},
    "high":   {"label": "15 · 15 · 10", "targets": {"Easy": 15, "Medium": 15, "Hard": 10}},
    "top":    {"label": "20 · 20 · 15", "targets": {"Easy": 20, "Medium": 20, "Hard": 15}},
}
DEFAULT_GOAL = "modest"

# Speed stages: target average seconds per question. Opened only after the hard rung clears.
SPEED_STAGES = {"S1": 240, "S2": 180, "S3": 150, "S4": 120}
SPEED_TIERS = ("Medium", "Hard")

# The learner picks one after a break; the app never assigns it.
BREAK_KINDS = {"concept": "Didn't know the concept", "calculation": "Calculation error",
               "reading": "Misread the question", "approach": "Wrong approach / strategy",
               "guess": "Guessed", "other": "Other"}

# Planning number: a streak tends to take a few times its target in questions.
# The method's published worked example used 49 questions for one 15-streak (about 3.3x).
BURN = 3.3


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def local_day(ts):
    return datetime.fromisoformat(ts).astimezone().date().isoformat()


def today():
    return datetime.now().astimezone().date().isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY,
  uid TEXT UNIQUE,                 -- any unique source key, e.g. <batch>:<n>
  section TEXT, topic TEXT, tier TEXT,
  stem TEXT, choices TEXT,         -- choices = JSON list of strings
  answer TEXT,                     -- the key: a choice letter A, B, C ...
  solution TEXT,
  src TEXT, stem_hash TEXT,
  added TEXT, retired INTEGER DEFAULT 0, flag TEXT);
CREATE INDEX IF NOT EXISTS items_scope ON items(section, topic, tier);
CREATE TABLE IF NOT EXISTS ladders(
  id INTEGER PRIMARY KEY,
  name TEXT, section TEXT, topic TEXT,   -- topic '*' = the whole section
  goal TEXT, targets TEXT,         -- targets = JSON {"Easy":n,"Medium":n,"Hard":n}
  rung TEXT,                       -- Easy | Medium | Hard | Done | S1..S4
  status TEXT DEFAULT 'active',    -- active | archived
  created TEXT, finished TEXT);
CREATE TABLE IF NOT EXISTS sittings(
  id INTEGER PRIMARY KEY, ladder_id INTEGER, started TEXT, ended TEXT);
CREATE TABLE IF NOT EXISTS served(
  item_id INTEGER PRIMARY KEY,     -- once served, never served again
  ladder_id INTEGER, rung TEXT, ts TEXT, skipped INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts(
  id INTEGER PRIMARY KEY,
  ladder_id INTEGER, sitting_id INTEGER, item_id INTEGER, rung TEXT,
  ts TEXT, given TEXT, correct INTEGER, guessed INTEGER DEFAULT 0,
  seconds REAL,
  counts INTEGER,                  -- 1 = extended the streak, 0 = broke it
  cause TEXT, cause_kind TEXT, cause_ts TEXT,   -- the learner's own words after a break
  note TEXT,                       -- optional note on a right answer
  voided INTEGER DEFAULT 0, void_reason TEXT);
CREATE INDEX IF NOT EXISTS attempts_ladder ON attempts(ladder_id, rung, id);
CREATE TABLE IF NOT EXISTS clears(
  id INTEGER PRIMARY KEY, ladder_id INTEGER, rung TEXT, ts TEXT,
  used INTEGER, breaks INTEGER, avg_seconds REAL);
CREATE TABLE IF NOT EXISTS jumps(  -- a rung skipped forward without a clear
  id INTEGER PRIMARY KEY, ladder_id INTEGER, from_rung TEXT, to_rung TEXT, ts TEXT);
"""


def db(path=None):
    con = sqlite3.connect(path or DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def load_taxonomy():
    """{"sections": {name: {"topics": {key: label}}}}. Read fresh on every call so edits apply live."""
    with open(TAXONOMY) as f:
        tax = json.load(f)
    tax.setdefault("sections", {})
    return tax


def topic_name(tax, section, topic):
    if topic in ("*", "", None):
        return "All topics"
    return tax["sections"].get(section, {}).get("topics", {}).get(topic, topic)


def stem_hash(stem, choices):
    norm = re.sub(r"\s+", " ", (stem or "").strip().lower()) + "|" + "|".join(c.strip().lower() for c in choices)
    return hashlib.sha1(norm.encode()).hexdigest()


def normalize_answer(s):
    return re.sub(r"[\s().]", "", str(s or "")).upper()


# ---------------------------------------------------------------- ladder arithmetic

def ladder_row(con, lid):
    r = con.execute("SELECT * FROM ladders WHERE id=?", (lid,)).fetchone()
    if not r:
        raise KeyError(f"no ladder {lid}")
    return r


def targets_of(lad):
    return json.loads(lad["targets"])


def rung_target(lad, rung):
    t = targets_of(lad)
    if rung in TIERS:
        return t[rung]
    if rung in SPEED_STAGES:
        return t["Medium"]    # a speed stage needs a streak as long as the medium rung's
    return 0


def rung_tiers(rung):
    return SPEED_TIERS if rung in SPEED_STAGES else (rung,)


def rung_label(rung):
    if rung in SPEED_STAGES:
        s = SPEED_STAGES[rung]
        return f"speed {rung[1]} ({s // 60}:{s % 60:02d} average)"
    return rung


def next_rung(rung):
    order = [*TIERS, "Done"]
    if rung in TIERS:
        return order[order.index(rung) + 1]
    if rung in SPEED_STAGES:
        stages = list(SPEED_STAGES)
        i = stages.index(rung)
        return stages[i + 1] if i + 1 < len(stages) else "Done"
    return "Done"


def rung_attempts(con, lid, rung):
    return con.execute("SELECT * FROM attempts WHERE ladder_id=? AND rung=? AND voided=0 ORDER BY id",
                       (lid, rung)).fetchall()


def current_streak(atts):
    n = 0
    for a in reversed(atts):
        if not a["counts"]:
            break
        n += 1
    return n


def longest_run(atts):
    best = cur = 0
    for a in atts:
        cur = cur + 1 if a["counts"] else 0
        best = max(best, cur)
    return best


def check_clear(con, lad, rung):
    """Return a clear record when the rung is done, else None. Accuracy rungs clear when the
    streak reaches the target. Speed stages also need the last `target` answers to average
    at or under the stage time."""
    atts = rung_attempts(con, lad["id"], rung)
    st, tgt = current_streak(atts), rung_target(lad, rung)
    if st < tgt or tgt <= 0:
        return None
    window = atts[-tgt:]
    avg = sum(a["seconds"] or 0 for a in window) / len(window)
    if rung in SPEED_STAGES and avg > SPEED_STAGES[rung]:
        return None
    breaks = sum(1 for a in atts if not a["counts"])
    con.execute("INSERT INTO clears(ladder_id, rung, ts, used, breaks, avg_seconds) VALUES(?,?,?,?,?,?)",
                (lad["id"], rung, now(), len(atts), breaks, round(avg, 1)))
    nr = next_rung(rung)
    con.execute("UPDATE ladders SET rung=?, finished=CASE WHEN ?='Done' THEN ? ELSE finished END WHERE id=?",
                (nr, nr, now(), lad["id"]))
    return dict(rung=rung, used=len(atts), breaks=breaks, avg_seconds=round(avg, 1), next=nr)


# ---------------------------------------------------------------- serving

def fresh_rows(con, lad, tiers):
    """Live items in the ladder's scope at these tiers that have never been served."""
    sql = f"""SELECT * FROM items i WHERE retired=0 AND section=? AND tier IN ({','.join('?' * len(tiers))})
              AND NOT EXISTS (SELECT 1 FROM served s WHERE s.item_id = i.id)"""
    args = [lad["section"], *tiers]
    if lad["topic"] not in ("*", "", None):
        sql += " AND topic=?"
        args.append(lad["topic"])
    return con.execute(sql, args).fetchall()


def pick_balanced(rows, rng=random):
    """Every topic with a fresh question is equally likely, so a large batch on one topic
    does not crowd out the rest of a section ladder."""
    by_topic = {}
    for r in rows:
        by_topic.setdefault(r["topic"], []).append(r)
    return rng.choice(by_topic[rng.choice(sorted(by_topic))])


def pending_item(con, lid):
    return con.execute("""SELECT i.*, s.rung srung FROM served s JOIN items i ON i.id = s.item_id
                          WHERE s.ladder_id=? AND s.skipped=0
                            AND NOT EXISTS (SELECT 1 FROM attempts t WHERE t.item_id = s.item_id)
                          ORDER BY s.ts DESC LIMIT 1""", (lid,)).fetchone()


def open_break(con, lid):
    """A break with no note written yet. The next question waits for it."""
    return con.execute("""SELECT * FROM attempts WHERE ladder_id=? AND counts=0 AND voided=0
                          AND (cause IS NULL OR TRIM(cause) = '') ORDER BY id DESC LIMIT 1""", (lid,)).fetchone()


def payload(r):
    """What the browser gets before answering. Never the key."""
    tax = load_taxonomy()
    return dict(item_id=r["id"], section=r["section"], tier=r["tier"],
                topic=topic_name(tax, r["section"], r["topic"]),
                stem=r["stem"], choices=json.loads(r["choices"]), uid=r["uid"])


def next_item(con, lid):
    lad = ladder_row(con, lid)
    if lad["status"] != "active":
        return {"error": "This ladder is archived."}
    ob = open_break(con, lid)
    if ob:
        return {"need_cause": ob["id"], "error": "Write what broke the streak first, in your own words."}
    p = pending_item(con, lid)
    if p and p["srung"] == lad["rung"]:
        return {"item": payload(p), "resumed": True}
    if p:   # the rung moved on under it; release it back to the bank
        con.execute("DELETE FROM served WHERE item_id=?", (p["id"],))
        con.commit()
    if lad["rung"] == "Done":
        return {"done": True}
    fresh = fresh_rows(con, lad, rung_tiers(lad["rung"]))
    if not fresh:
        return {"empty": True, "rung": lad["rung"],
                "error": f"No fresh questions left for the {rung_label(lad['rung'])} rung of this ladder. "
                         f"Add questions with import_items.py."}
    it = pick_balanced(fresh)
    con.execute("INSERT INTO served(item_id, ladder_id, rung, ts) VALUES(?,?,?,?)", (it["id"], lid, lad["rung"], now()))
    con.commit()
    return {"item": payload(it), "resumed": False}


def record_answer(con, body):
    lid, iid = int(body["ladder_id"]), int(body["item_id"])
    lad = ladder_row(con, lid)
    srow = con.execute("SELECT * FROM served WHERE item_id=? AND ladder_id=?", (iid, lid)).fetchone()
    if not srow:
        return {"error": "That question was not served on this ladder."}
    if con.execute("SELECT 1 FROM attempts WHERE item_id=?", (iid,)).fetchone():
        return {"error": "Already answered."}
    it = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    given = str(body.get("given", ""))
    correct = normalize_answer(given) == normalize_answer(it["answer"])
    guessed = bool(body.get("guessed"))
    counts = correct and not guessed      # a lucky guess is not mastery, so it breaks the streak
    rung = srow["rung"]
    before = current_streak(rung_attempts(con, lid, rung))
    cur = con.execute("""INSERT INTO attempts(ladder_id, sitting_id, item_id, rung, ts, given, correct, guessed,
                         seconds, counts) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (lid, body.get("sitting_id"), iid, rung, now(), given, int(correct), int(guessed),
                       float(body.get("seconds") or 0), int(counts)))
    aid = cur.lastrowid
    clear = check_clear(con, lad, rung) if counts else None
    con.commit()
    return dict(attempt_id=aid, correct=correct, guessed=guessed, counts=counts,
                answer=it["answer"], given=given, solution=it["solution"] or "",
                streak=current_streak(rung_attempts(con, lid, rung)), broke_at=0 if counts else before,
                target=rung_target(lad, rung), rung=rung, clear=clear, state=state(con, lid))


def state(con, lid):
    """Everything the ladder screen and the tracker show."""
    lad = ladder_row(con, lid)
    tax = load_taxonomy()
    rungs = [*TIERS] + [s for s in SPEED_STAGES if lad["rung"] == s or con.execute(
        "SELECT 1 FROM attempts WHERE ladder_id=? AND rung=? LIMIT 1", (lid, s)).fetchone()]
    out, all_today, day = [], [], today()
    for rg in rungs:
        atts = rung_attempts(con, lid, rg)
        all_today += [a for a in atts if local_day(a["ts"]) == day]
        runs, cur = [], []
        for a in atts:
            cur.append(dict(n=len(cur) + 1 if a["counts"] else None, attempt_id=a["id"], item_id=a["item_id"],
                            correct=bool(a["correct"]), guessed=bool(a["guessed"]), counts=bool(a["counts"]),
                            seconds=a["seconds"]))
            if not a["counts"]:
                runs.append(dict(items=cur, broken=True, cause=a["cause"] or "", kind=a["cause_kind"],
                                 attempt_id=a["id"]))
                cur = []
        clear = con.execute("SELECT * FROM clears WHERE ladder_id=? AND rung=? ORDER BY id DESC LIMIT 1",
                            (lid, rg)).fetchone()
        if cur:
            runs.append(dict(items=cur, broken=False, cause=""))
        out.append(dict(rung=rg, label=rung_label(rg), target=rung_target(lad, rg), used=len(atts),
                        breaks=sum(1 for a in atts if not a["counts"]), streak=current_streak(atts),
                        longest=longest_run(atts), cleared=dict(clear) if clear else None, runs=runs,
                        cap=SPEED_STAGES.get(rg)))
    rung = lad["rung"]
    cur_rung = next((r for r in out if r["rung"] == rung), None)
    speed_avg = None
    if rung in SPEED_STAGES and cur_rung and cur_rung["streak"]:
        atts = rung_attempts(con, lid, rung)
        win = atts[-min(cur_rung["streak"], cur_rung["target"]):]
        speed_avg = round(sum(a["seconds"] or 0 for a in win) / len(win), 1)
    fresh = {}
    if lad["status"] == "active":
        later = [t for t in TIERS if rung in TIERS and TIERS.index(t) > TIERS.index(rung)]
        for rg in ([rung] if rung != "Done" else []) + later:
            fresh[rg] = len(fresh_rows(con, lad, rung_tiers(rg)))
    sit = con.execute("SELECT * FROM sittings WHERE ladder_id=? AND ended IS NULL ORDER BY id DESC LIMIT 1",
                      (lid,)).fetchone()
    ob = open_break(con, lid)
    return dict(id=lad["id"], name=lad["name"], section=lad["section"], topic=lad["topic"],
                topic_name=topic_name(tax, lad["section"], lad["topic"]),
                goal=lad["goal"], goal_label=GOALS.get(lad["goal"], {}).get("label", "custom"),
                targets=targets_of(lad), rung=rung, rung_label=rung_label(rung),
                status=lad["status"], created=lad["created"], finished=lad["finished"],
                streak=cur_rung["streak"] if cur_rung else 0, target=cur_rung["target"] if cur_rung else 0,
                longest_today=longest_run(sorted(all_today, key=lambda a: a["id"])),
                sitting=dict(sit) if sit else None, speed_avg=speed_avg,
                open_break=dict(ob) if ob else None, rungs=out, fresh=fresh, burn=BURN)


def create_ladder(con, body):
    tax = load_taxonomy()
    section = body.get("section")
    if section not in tax["sections"]:
        return {"error": "Pick a section."}
    topic = body.get("topic") or "*"
    if topic != "*" and topic not in tax["sections"][section].get("topics", {}):
        return {"error": f"{topic} is not a topic of {section}."}
    goal = body.get("goal") or DEFAULT_GOAL
    if goal == "custom":
        t = body.get("targets") or {}
        try:
            targets = {k: max(1, min(50, int(t[k]))) for k in TIERS}
        except (KeyError, ValueError, TypeError):
            return {"error": "Custom targets need Easy, Medium and Hard numbers."}
    elif goal in GOALS:
        targets = GOALS[goal]["targets"]
    else:
        return {"error": "Unknown goal."}
    name = body.get("name") or f"{section} · {topic_name(tax, section, topic)}"
    cur = con.execute("""INSERT INTO ladders(name, section, topic, goal, targets, rung, created)
                         VALUES(?,?,?,?,?,?,?)""",
                      (name, section, topic, goal, json.dumps(targets), "Easy", now()))
    con.commit()
    return {"id": cur.lastrowid}


def catalog(con):
    """Sections and topics from taxonomy.json, with live fresh counts per tier from the bank."""
    tax = load_taxonomy()
    counts = {}
    for r in con.execute("""SELECT section, topic, tier, COUNT(*) n FROM items i WHERE retired=0
                            AND NOT EXISTS (SELECT 1 FROM served s WHERE s.item_id = i.id)
                            GROUP BY section, topic, tier"""):
        counts.setdefault((r["section"], r["topic"]), {})[r["tier"]] = r["n"]
    sections = []
    for sec, spec in tax["sections"].items():
        topics = [dict(key=k, name=v, fresh=counts.get((sec, k), {})) for k, v in spec.get("topics", {}).items()]
        total = {t: sum(tp["fresh"].get(t, 0) for tp in topics) for t in TIERS}
        sections.append(dict(name=sec, topics=topics, fresh=total))
    return dict(sections=sections, goals=GOALS, default_goal=DEFAULT_GOAL, tiers=TIERS,
                speed=SPEED_STAGES, break_kinds=BREAK_KINDS)


def home(con):
    lads = [state(con, r["id"]) for r in con.execute("SELECT id FROM ladders ORDER BY status='archived', id DESC")]
    for l in lads:
        for r in l["rungs"]:
            r.pop("runs", None)   # the home cards need the counts, not every run
    bank = [dict(r) for r in con.execute("""SELECT section, COUNT(*) n FROM items WHERE retired=0
                                            GROUP BY section ORDER BY section""")]
    kinds = {r[0] or "untyped": r[1] for r in con.execute(
        "SELECT cause_kind, COUNT(*) FROM attempts WHERE counts=0 AND voided=0 GROUP BY cause_kind")}
    recent = [dict(r) for r in con.execute("""SELECT t.cause, t.cause_kind kind, t.ts, t.rung, l.name ladder
            FROM attempts t JOIN ladders l ON l.id = t.ladder_id
            WHERE t.counts=0 AND t.voided=0 AND t.cause IS NOT NULL ORDER BY t.id DESC LIMIT 8""")]
    return dict(ladders=lads, bank=bank, today=today(),
                breaks=dict(kinds=kinds, recent=recent, labels=BREAK_KINDS))


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        con = db()
        try:
            if u.path in ("/", "/index.html"):
                data = open(UI, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            elif u.path == "/api/home":
                self._json(home(con))
            elif u.path == "/api/catalog":
                self._json(catalog(con))
            elif m := re.fullmatch(r"/api/ladder/(\d+)", u.path):
                self._json(state(con, int(m.group(1))))
            elif u.path == "/api/attempt":
                a = con.execute("SELECT * FROM attempts WHERE id=?", (int(q["id"]),)).fetchone()
                if not a:
                    raise KeyError("no such attempt")
                it = con.execute("SELECT * FROM items WHERE id=?", (a["item_id"],)).fetchone()
                self._json(dict(attempt=dict(a), item=payload(it), answer=it["answer"], solution=it["solution"] or ""))
            else:
                self._json({"error": "not found"}, 404)
        except KeyError as e:
            self._json({"error": str(e)}, 404)
        except (ValueError, TypeError) as e:
            self._json({"error": f"bad request: {e}"}, 400)
        finally:
            con.close()

    def do_POST(self):
        u = urlparse(self.path)
        con = db()
        try:
            b = self._body()
            if u.path == "/api/ladder":
                self._json(create_ladder(con, b))
            elif m := re.fullmatch(r"/api/ladder/(\d+)/next", u.path):
                self._json(next_item(con, int(m.group(1))))
            elif m := re.fullmatch(r"/api/ladder/(\d+)/archive", u.path):
                con.execute("UPDATE ladders SET status=? WHERE id=?",
                            ("active" if b.get("restore") else "archived", int(m.group(1))))
                con.commit()
                self._json({"ok": True})
            elif m := re.fullmatch(r"/api/ladder/(\d+)/jump", u.path):
                # Override: move forward to a later accuracy rung without clearing the ones between.
                # No clears row is written, so skipped rungs stay "not cleared"; the jump is logged.
                lad = ladder_row(con, int(m.group(1)))
                to = b.get("rung", "Hard")
                if lad["rung"] not in TIERS or to not in TIERS or TIERS.index(to) <= TIERS.index(lad["rung"]):
                    return self._json({"error": f"Can only skip forward from Easy or Medium (now {lad['rung']})."})
                con.execute("INSERT INTO jumps(ladder_id, from_rung, to_rung, ts) VALUES(?,?,?,?)",
                            (lad["id"], lad["rung"], to, now()))
                con.execute("UPDATE ladders SET rung=? WHERE id=?", (to, lad["id"]))
                con.commit()
                self._json({"rung": to})
            elif m := re.fullmatch(r"/api/ladder/(\d+)/speed", u.path):
                lad = ladder_row(con, int(m.group(1)))
                if lad["rung"] != "Done":
                    return self._json({"error": "Speed stages open after the hard rung clears."})
                done = {r[0] for r in con.execute("SELECT rung FROM clears WHERE ladder_id=?", (lad["id"],))}
                stage = next((s for s in SPEED_STAGES if s not in done), None)
                if not stage:
                    return self._json({"error": "All speed stages are cleared."})
                con.execute("UPDATE ladders SET rung=? WHERE id=?", (stage, lad["id"]))
                con.commit()
                self._json({"rung": stage})
            elif u.path == "/api/sitting/start":
                lid = int(b["ladder_id"])
                con.execute("UPDATE sittings SET ended=? WHERE ladder_id=? AND ended IS NULL", (now(), lid))
                cur = con.execute("INSERT INTO sittings(ladder_id, started) VALUES(?,?)", (lid, now()))
                con.commit()
                self._json({"sitting_id": cur.lastrowid, "started": now()})
            elif u.path == "/api/sitting/end":
                con.execute("UPDATE sittings SET ended=? WHERE id=? AND ended IS NULL", (now(), int(b["sitting_id"])))
                con.commit()
                self._json({"ok": True})
            elif u.path == "/api/answer":
                self._json(record_answer(con, b))
            elif u.path == "/api/cause":
                text = (b.get("text") or "").strip()
                if len(text) < 3:
                    return self._json({"error": "A few words, in your own words."})
                kind = b.get("kind") if b.get("kind") in BREAK_KINDS else None
                n = con.execute("UPDATE attempts SET cause=?, cause_kind=?, cause_ts=? WHERE id=? AND counts=0",
                                (text, kind, now(), int(b["attempt_id"]))).rowcount
                con.commit()
                self._json({"ok": bool(n)} if n else {"error": "No break with that id."})
            elif u.path == "/api/note":
                con.execute("UPDATE attempts SET note=? WHERE id=?", ((b.get("text") or "").strip(), int(b["attempt_id"])))
                con.commit()
                self._json({"ok": True})
            elif u.path == "/api/void":
                # A wrong key or a broken item: the attempt stops counting either way and the
                # question leaves the bank. The streak is recomputed as if it never happened.
                a = con.execute("SELECT * FROM attempts WHERE id=?", (int(b["attempt_id"]),)).fetchone()
                if not a:
                    raise KeyError("no such attempt")
                reason = (b.get("reason") or "").strip() or "voided"
                con.execute("UPDATE attempts SET voided=1, void_reason=? WHERE id=?", (reason, a["id"]))
                con.execute("UPDATE items SET retired=1, flag=? WHERE id=?", (reason, a["item_id"]))
                lad = ladder_row(con, a["ladder_id"])
                clear = check_clear(con, lad, a["rung"]) if lad["rung"] == a["rung"] else None
                con.commit()
                self._json({"ok": True, "clear": clear})
            elif u.path == "/api/skip":
                # Before answering: the item is unreadable or broken. No streak effect.
                iid = int(b["item_id"])
                reason = (b.get("reason") or "").strip() or "skipped: broken item"
                con.execute("UPDATE served SET skipped=1 WHERE item_id=?", (iid,))
                con.execute("UPDATE items SET retired=1, flag=? WHERE id=?", (reason, iid))
                con.commit()
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)
        except KeyError as e:
            self._json({"error": f"not found or missing field: {e}"}, 400)
        except (ValueError, TypeError) as e:
            self._json({"error": f"bad request: {e}"}, 400)
        finally:
            con.close()


def cmd_serve(args):
    db().close()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Streaks Trainer on {url}  (Ctrl-C to stop)   database: {DB}")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_status(_args):
    con = db()
    h = home(con)
    print(f"Streaks Trainer · {h['today']}   database: {DB}")
    print("\nBANK (live items)")
    if not h["bank"]:
        print("  empty: run make_sample_bank.py or import_items.py")
    for b in h["bank"]:
        print(f"  {b['section']:<12} {b['n']:>5}")
    print("\nLADDERS")
    if not h["ladders"]:
        print("  none yet: open the app and start one")
    for l in h["ladders"]:
        t = l["targets"]
        print(f"  #{l['id']} {l['name']}  [{l['status']}]  targets {t['Easy']}/{t['Medium']}/{t['Hard']}")
        print(f"      rung {l['rung_label']}: streak {l['streak']}/{l['target']}   longest today {l['longest_today']}"
              f"   fresh left {l['fresh']}")


def main():
    import report
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve"); p.add_argument("--port", type=int, default=PORT); p.add_argument("--open", action="store_true"); p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("report"); report.add_args(p); p.set_defaults(fn=report.run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
