#!/usr/bin/env python3
"""`streaks.py report`: per-ladder numbers and break patterns, printed from the database, read-only.

Counts only. It never prints a stem, choice, key or solution. A miss = wrong, or right but guessed;
voided answers are left out. The database is opened read-only, so nothing here can write it.

  python3 streaks.py report [--since YYYY-MM-DD]
"""
import os, sqlite3, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import streaks as S


def pct(clean, n):
    return f"{clean:>3}/{n:<3} {round(100 * clean / n):>3}%" if n else f"{'-':>13}"


def run(args):
    if not os.path.exists(S.DB):
        sys.exit(f"no database at {S.DB}")
    con = sqlite3.connect(f"file:{S.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = 1")
    since = args.since or ""
    rows = [dict(r) for r in con.execute(
        """SELECT a.ladder_id, a.rung, a.ts, a.counts, a.seconds, a.cause_kind, i.section, i.topic, i.tier
           FROM attempts a JOIN items i ON i.id = a.item_id WHERE a.voided = 0 ORDER BY a.id""")]
    rows = [r for r in rows if S.local_day(r["ts"]) >= since] if since else rows
    print(f"Streaks report · {S.today()}" + (f" · since {since}" if since else ""))

    print("\nCLEAN ANSWERS BY SECTION AND TIER")
    by = Counter((r["section"], r["tier"]) for r in rows)
    clean = Counter((r["section"], r["tier"]) for r in rows if r["counts"])
    for sec in sorted({k[0] for k in by}):
        print(f"  {sec:<12} " + "  ".join(f"{t}: {pct(clean[(sec, t)], by[(sec, t)])}" for t in S.TIERS))

    print("\nLADDERS (questions used per rung, breaks, and used / target = the real burn rate)")
    for lad in con.execute("SELECT * FROM ladders ORDER BY id"):
        t = S.targets_of(lad)
        print(f"  #{lad['id']} {lad['name']}  [{lad['status']}]  now {S.rung_label(lad['rung'])}")
        for rung in [*S.TIERS, *S.SPEED_STAGES]:
            rr = [r for r in rows if r["ladder_id"] == lad["id"] and r["rung"] == rung]
            if not rr:
                continue
            tgt = t["Medium"] if rung in S.SPEED_STAGES else t[rung]
            breaks = sum(1 for r in rr if not r["counts"])
            avg = sum(r["seconds"] or 0 for r in rr) / len(rr)
            print(f"      {rung:<6} used {len(rr):>3}  breaks {breaks:>3}  burn {len(rr) / tgt:4.1f}x  "
                  f"avg {avg:5.0f}s")

    print("\nWHAT BROKE THE STREAKS (the learner's own break types)")
    kinds = Counter(r["cause_kind"] or "untyped" for r in rows if not r["counts"])
    if not kinds:
        print("  no breaks yet")
    for k, n in kinds.most_common():
        print(f"  {S.BREAK_KINDS.get(k, k):<28} {n:>4}")
    con.close()


def add_args(p):
    p.add_argument("--since", help="only answers on or after this local date (YYYY-MM-DD)")
