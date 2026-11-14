# Item format

Questions enter the bank through `python3 import_items.py FILE [--dry-run]`, from CSV or JSON. This page is the contract for those files. `sample/example.csv` is a working CSV example; `make_sample_bank.py` writes `sample/sample-items.json`, a complete JSON example.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `section` | yes | A section name from `taxonomy.json`, e.g. `Math` |
| `topic` | yes | A topic key of that section, e.g. `algebra` |
| `difficulty` | yes | `Easy`, `Medium` or `Hard` (any capitalization; `tier` is accepted as an alias) |
| `stem` | yes | The question text. Line breaks are kept. |
| `choices` | yes | 2 to 8 distinct, non-empty answer choices, in display order |
| `key` | yes | The letter of the right choice: `A` is the first (`answer` is accepted as an alias) |
| `explanation` | no | Shown after the learner answers (`solution` is accepted as an alias) |

## JSON

Either a list of items or an object with an `items` list:

```json
{
  "items": [
    {
      "section": "Math",
      "topic": "algebra",
      "difficulty": "Easy",
      "stem": "If 3x = 21, what is x?",
      "choices": ["6", "7", "8", "18"],
      "key": "B",
      "explanation": "Divide both sides by 3."
    }
  ]
}
```

## CSV

One row per question, with a header row. Choices go in `choice_a` to `choice_h`; leave unused ones out or empty.

```csv
section,topic,difficulty,stem,choice_a,choice_b,choice_c,choice_d,key,explanation
Math,algebra,Easy,"If 3x = 21, what is x?",6,7,8,18,B,Divide both sides by 3.
```

## What the importer checks

- `section` and `topic` exist in `taxonomy.json`. To add a subject, add its section and topic keys there first.
- `difficulty` is one of the three tiers.
- The stem is not empty; there are 2 to 8 distinct choices; the key is a letter inside the choice range.
- A question whose stem and choices (whitespace and case ignored) are already in the bank is skipped as a duplicate.

Every rejected row is reported with its number and reason. The command exits with status 1 if any row was rejected. With `--dry-run` nothing is written.

## In the database

Each item becomes a row of `items` (see `SCHEMA` in `streaks.py`): `choices` is stored as a JSON list, `answer` as the key letter, `solution` as the explanation, `src` as the file name it came from. Items are never deleted; a voided or skipped item is marked `retired = 1` with a reason in `flag`.
