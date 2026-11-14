#!/usr/bin/env python3
"""Load your own multiple-choice questions into the streak bank from a CSV or JSON file.

Usage:
    python3 import_items.py my_questions.csv [--dry-run] [--db PATH]
    python3 import_items.py my_questions.json [--dry-run]

Every item needs: section, topic, difficulty (Easy | Medium | Hard), stem, choices, key.
`explanation` is optional but recommended: it is shown after each answer.

CSV: one row per question with the columns
    section, topic, difficulty, stem, choice_a, choice_b, ... (up to choice_h), key, explanation
JSON: either a list of items or {"items": [...]}, each item
    {"section": "Math", "topic": "algebra", "difficulty": "Easy", "stem": "...",
     "choices": ["...", "..."], "key": "B", "explanation": "..."}

`key` is the letter of the right choice (A = first). Section and topic must exist in taxonomy.json
(add them there first). A question whose stem and choices are already in the bank is skipped.
With --dry-run nothing is written; every problem is still reported.
"""
import argparse, csv, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import streaks as S

LETTERS = "ABCDEFGH"


def read_rows(path):
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as f:
            out = []
            for r in csv.DictReader(f):
                r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                r["choices"] = [r[f"choice_{c.lower()}"] for c in LETTERS if r.get(f"choice_{c.lower()}")]
                out.append(r)
            return out
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("JSON must be a list of items or an object with an 'items' list")
    return items


def validate(r, tax):
    """Return (clean item, None) or (None, reason)."""
    if not isinstance(r, dict):
        return None, "not an object"
    sec, topic = str(r.get("section", "")).strip(), str(r.get("topic", "")).strip()
    tier = str(r.get("difficulty") or r.get("tier") or "").strip().capitalize()
    stem, key = str(r.get("stem", "")).strip(), str(r.get("key") or r.get("answer") or "").strip().upper()
    choices = r.get("choices")
    if sec not in tax["sections"]:
        return None, f"unknown section {sec!r} (add it to taxonomy.json)"
    if topic not in tax["sections"][sec].get("topics", {}):
        return None, f"unknown topic {topic!r} in {sec} (add it to taxonomy.json)"
    if tier not in S.TIERS:
        return None, f"difficulty must be Easy, Medium or Hard, got {tier!r}"
    if not stem:
        return None, "empty stem"
    if not isinstance(choices, list) or not 2 <= len(choices) <= len(LETTERS):
        return None, f"need 2 to {len(LETTERS)} choices"
    choices = [str(c).strip() for c in choices]
    if any(not c for c in choices) or len(set(c.lower() for c in choices)) != len(choices):
        return None, "choices must be non-empty and distinct"
    if len(key) != 1 or key not in LETTERS[:len(choices)]:
        return None, f"key must be one of {LETTERS[:len(choices)]}, got {key!r}"
    return dict(section=sec, topic=topic, tier=tier, stem=stem, choices=choices, answer=key,
                solution=str(r.get("explanation") or r.get("solution") or "").strip()), None


def import_file(path, dry_run=False, db_path=None, src=None):
    tax = S.load_taxonomy()
    rows = read_rows(path)
    con = S.db(db_path)
    have = {h for (h,) in con.execute("SELECT stem_hash FROM items")}
    batch = src or os.path.splitext(os.path.basename(path))[0]
    added, dupes, bad = 0, 0, []
    for n, r in enumerate(rows, 1):
        it, why = validate(r, tax)
        if why:
            bad.append((n, why))
            continue
        h = S.stem_hash(it["stem"], it["choices"])
        if h in have:
            dupes += 1
            continue
        have.add(h)
        added += 1
        if not dry_run:
            con.execute("""INSERT INTO items(uid, section, topic, tier, stem, choices, answer, solution, src,
                           stem_hash, added) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (f"{batch}:{h[:12]}", it["section"], it["topic"], it["tier"], it["stem"],
                         json.dumps(it["choices"], ensure_ascii=False), it["answer"], it["solution"],
                         batch, h, S.now()))
    if not dry_run:
        con.commit()
    con.close()
    for n, why in bad:
        print(f"  item {n}: rejected, {why}")
    verb = "would add" if dry_run else "added"
    print(f"{path}: {len(rows)} read, {verb} {added}, {dupes} duplicate, {len(bad)} rejected")
    return added, dupes, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="a .csv or .json file")
    ap.add_argument("--dry-run", action="store_true", help="validate and count, write nothing")
    ap.add_argument("--db", help=f"database path (default {S.DB}, or $STREAKS_DB)")
    a = ap.parse_args()
    _, _, bad = import_file(a.file, a.dry_run, a.db)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
