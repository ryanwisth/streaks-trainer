#!/usr/bin/env python3
"""Build a small demo bank from the original questions in sample/sample_questions.py.

Usage:
    python3 make_sample_bank.py            # writes streaks.db beside this file (or $STREAKS_DB)

It builds the questions (every key is checked by code; see sample/sample_questions.py), writes them to
sample/sample-items.json in the import_items.py JSON shape, and loads that file through the same
importer a learner uses for their own questions. Re-running it is safe: duplicates are skipped.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "sample"))

from sample_questions import build   # noqa: E402
import import_items                  # noqa: E402
import streaks                       # noqa: E402


def main():
    items = build()
    path = os.path.join(HERE, "sample", "sample-items.json")
    with open(path, "w") as f:
        json.dump({"items": items}, f, indent=1, ensure_ascii=False)
    print(f"database: {streaks.DB}")
    import_items.import_file(path, src="sample")


if __name__ == "__main__":
    main()
