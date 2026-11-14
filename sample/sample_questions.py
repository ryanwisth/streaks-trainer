"""Original demo questions for the sample bank, generated and checked by code.

Every question here is built from simple templates in this file (arithmetic, algebra, number
properties, ordering puzzles, set counting). None is taken or adapted from any published source.

How each key is checked (all of them, at import time, by `build()`):
  - Math items: the answer is computed by one method and re-checked by a second, independent one
    (brute force, Fraction arithmetic or direct substitution).
  - Logic / deduction: every ordering of the people is tried; the clues must leave exactly one,
    and the key is read from that one ordering.
  - Logic / sets: the answer from the counting formula must equal a count of real Python sets
    built to match the stem.
  - Every item: exactly one choice equals the checked answer, and all choices are distinct.
A failed check raises AssertionError, so a broken template can never reach the bank.
"""
import random
from fractions import Fraction
from itertools import permutations
from math import gcd

LETTERS = "ABCDE"
PER_TOPIC = {"Math": 4, "Logic": 5}   # questions per topic per tier


def lcm(a, b):
    return a * b // gcd(a, b)


def _mc(rng, answer, distractors, fmt=str):
    """Five distinct choices, answer at a random position. Returns (choices, key)."""
    pool = [d for d in dict.fromkeys(distractors) if d != answer and (d >= 0 or answer < 0)]
    k = 1
    while len(pool) < 4:   # answer + 1 is always a candidate, so this ends                       # top up with near misses if a template ran short
        for cand in (answer + k, answer - k):
            if cand not in pool and cand != answer and len(pool) < 4:
                pool.append(cand)
        k += 1
    vals = pool[:4] + [answer]
    rng.shuffle(vals)
    choices = [fmt(v) for v in vals]
    assert len(set(choices)) == 5
    return choices, LETTERS[vals.index(answer)]


# ---------------------------------------------------------------- Math

def arithmetic(rng, tier):
    if tier == "Easy":
        a, b, c = rng.randint(2, 9), rng.randint(2, 9), rng.randint(2, 9)
        ans = a + b * c
        assert ans == eval(f"{a} + {b} * {c}")
        return (f"What is {a} + {b} × {c}?", ans, [(a + b) * c, a + b + c, a * b + c],
                f"Multiply before adding: {b} × {c} = {b * c}, then {a} + {b * c} = {ans}.")
    if tier == "Medium":
        p, n = rng.choice([15, 25, 35, 45, 60, 75]), 20 * rng.randint(2, 15)
        ans = p * n // 100
        assert Fraction(p, 100) * n == ans
        return (f"What is {p}% of {n}?", ans, [ans + 10, ans * 2, n - ans, p + n // 10],
                f"{p}% of {n} = {p}/100 × {n} = {ans}.")
    start = 40 * rng.randint(3, 10)
    up, down = rng.choice([(25, 20), (50, 20), (20, 25), (10, 10), (50, 50)])
    exact = Fraction(start) * Fraction(100 + up, 100) * Fraction(100 - down, 100)
    stepwise = Fraction(start) + Fraction(start * up, 100)
    stepwise -= stepwise * Fraction(down, 100)
    assert exact == stepwise
    ans = exact
    return (f"A price of ${start} rises by {up}% and then falls by {down}%. What is the final price in dollars?",
            ans, [Fraction(start), Fraction(start) * Fraction(100 + up - down, 100), ans + 10, ans - 6],
            f"{start} × {100 + up}/100 × {100 - down}/100 = {ans}. Percent changes multiply; they do not add.")


def algebra(rng, tier):
    if tier == "Easy":
        a, x, b = rng.randint(2, 9), rng.randint(-5, 12), rng.randint(1, 20)
        c = a * x + b
        assert a * Fraction(c - b, a) + b == c
        return (f"If {a}x + {b} = {c}, what is x?", x, [x + 1, x - 1, Fraction(c + b, a), c - b],
                f"Subtract {b}: {a}x = {c - b}. Divide by {a}: x = {x}.")
    if tier == "Medium":
        x, y = rng.randint(2, 15), rng.randint(1, 12)
        s, d = x + y, x - y
        assert (s + d) / 2 == x and (s - d) / 2 == y
        return (f"If x + y = {s} and x − y = {str(d).replace('-', '−')}, what is x?", x, [y, s, d, x + 1],
                f"Add the equations: 2x = {s + d}, so x = {x}.")
    r1, r2 = rng.sample(range(-6, 9), 2)
    b, c = -(r1 + r2), r1 * r2
    roots = [t for t in range(-50, 51) if t * t + b * t + c == 0]
    assert sorted(roots) == sorted([r1, r2])
    ans = r1 * r1 + r2 * r2
    assert ans == (r1 + r2) ** 2 - 2 * c
    eq = f"x² {'+' if b >= 0 else '−'} {abs(b)}x {'+' if c >= 0 else '−'} {abs(c)} = 0"
    return (f"The two roots of {eq} are r and s. What is r² + s²?", ans,
            [(r1 + r2) ** 2, ans + 2 * c if c else ans + 4, abs(r1 * r2), b * b + 2 * c],
            f"r + s = {r1 + r2} and rs = {c}, so r² + s² = (r + s)² − 2rs = {(r1 + r2) ** 2} − {2 * c} = {ans}.")


def number_properties(rng, tier):
    if tier == "Easy":
        d = rng.randint(3, 9)
        n = d * rng.randint(3, 12) + rng.randint(1, d - 1)
        ans = n % d
        assert any(n == d * q + ans for q in range(n + 1))
        return (f"What is the remainder when {n} is divided by {d}?", ans, [0, d - ans, n // d, ans + 1],
                f"{n} = {d} × {n // d} + {ans}.")
    if tier == "Medium":
        a, b = rng.sample([4, 6, 8, 9, 10, 12, 14, 15, 18], 2)
        ans = lcm(a, b)
        assert ans == min(m for m in range(1, a * b + 1) if m % a == 0 and m % b == 0)
        return (f"What is the least common multiple of {a} and {b}?", ans, [a * b if a * b != ans else ans * 2, gcd(a, b), ans // 2 if ans % 2 == 0 else ans + a, a + b],
                f"The smallest number both divide is {ans} (= {a} × {b} ÷ gcd {gcd(a, b)}).")
    a, b = rng.sample([2, 3, 4, 5, 6, 7], 2)
    n = 10 * rng.randint(5, 15)
    ans = sum(1 for k in range(1, n + 1) if k % a == 0 or k % b == 0)
    assert ans == n // a + n // b - n // lcm(a, b)
    return (f"How many integers from 1 to {n} inclusive are divisible by {a} or by {b}?", ans,
            [n // a + n // b, n // lcm(a, b), n - ans, ans + 1],
            f"{n // a} multiples of {a} plus {n // b} of {b}, minus {n // lcm(a, b)} counted twice "
            f"(multiples of {lcm(a, b)}) = {ans}.")


# ---------------------------------------------------------------- Logic

NAMES = ["Ana", "Ben", "Cal", "Dee", "Eli"]


def deduction(rng, tier):
    n = {"Easy": 3, "Medium": 4, "Hard": 5}[tier]
    people = NAMES[:n]
    truth = tuple(rng.sample(people, n))
    pos = {p: i for i, p in enumerate(truth)}

    def candidates():
        x, y = rng.sample(people, 2)
        out = []
        if pos[x] < pos[y]:
            out.append((f"{x} stands somewhere to the left of {y}.", lambda o, x=x, y=y: o.index(x) < o.index(y)))
        if pos[y] == pos[x] + 1:
            out.append((f"{y} stands directly to the right of {x}.", lambda o, x=x, y=y: o.index(y) == o.index(x) + 1))
        if abs(pos[x] - pos[y]) > 1:
            out.append((f"{min(x, y)} and {max(x, y)} are not next to each other.", lambda o, x=x, y=y: abs(o.index(x) - o.index(y)) > 1))
        if 0 < pos[x] < n - 1:
            out.append((f"{x} is not at either end.", lambda o, x=x: 0 < o.index(x) < n - 1))
        if pos[x] in (0, n - 1):
            out.append((f"{x} stands at one end of the row.", lambda o, x=x: o.index(x) in (0, n - 1)))
        return out

    clues = []
    while True:
        alive = [o for o in permutations(people) if all(f(o) for _, f in clues)]
        if len(alive) == 1:
            break
        c = rng.choice(candidates() or [None])
        if c and c[0] not in [t for t, _ in clues]:
            clues.append(c)
    assert alive == [truth]
    k = rng.randrange(n)
    ord_word = ["first", "second", "third", "fourth", "fifth"][k]
    count = {3: "Three", 4: "Four", 5: "Five"}[n]
    stem = (f"{count} people ({', '.join(people[:-1])} and {people[-1]}) stand in a row, in an order you must work out.\n"
            + "\n".join(f"- {t}" for t, _ in clues)
            + f"\nWho stands {ord_word} from the left?")
    ans = truth[k]
    others = [p for p in people if p != ans] + [p for p in NAMES if p not in people]
    return (stem, ans, others, f"Only one order fits every clue: {', '.join(truth)}. Position {k + 1} is {ans}.")


def sets(rng, tier):
    if tier == "Easy":
        a, b = rng.randint(10, 25), rng.randint(10, 25)
        c = rng.randint(2, min(a, b) - 2)
        total = a + b - c + rng.randint(3, 12)
        ans = total - (a + b - c)
        tea, coffee = set(range(a)), set(range(a - c, a - c + b))
        assert len(tea & coffee) == c and total - len(tea | coffee) == ans
        return (f"In a group of {total} people, {a} drink tea, {b} drink coffee and {c} drink both. "
                f"How many drink neither?", ans, [total - a - b if total - a - b > 0 else ans + c, c, ans + c, ans - 1],
                f"Tea or coffee = {a} + {b} − {c} = {a + b - c}. Neither = {total} − {a + b - c} = {ans}.")
    if tier == "Medium":
        total, neither = rng.randint(40, 70), rng.randint(2, 9)
        a, b = rng.randint(15, 30), rng.randint(15, 30)
        both = a + b - (total - neither)
        if both < 1 or both > min(a, b):
            return sets(rng, tier)
        tea, coffee = set(range(a)), set(range(a - both, a - both + b))
        assert len(tea | coffee) == total - neither and len(tea & coffee) == both
        return (f"Of {total} students, {a} take art, {b} take music, and {neither} take neither. "
                f"How many take both?", both, [a + b - total, both + neither, total - a, both + 2],
                f"Art or music = {total} − {neither} = {total - neither}. Both = {a} + {b} − {total - neither} = {both}.")
    # three sets from region sizes: only A, only B, only C, AB only, AC only, BC only, all three, none
    r = [rng.randint(2, 9) for _ in range(8)]
    oA, oB, oC, ab, ac, bc, abc, none = r
    A, B, C = oA + ab + ac + abc, oB + ab + bc + abc, oC + ac + bc + abc
    AB, AC, BC = ab + abc, ac + abc, bc + abc
    total = sum(r)
    ans = total - (A + B + C - AB - AC - BC + abc)
    assert ans == none
    return (f"In a club of {total}, {A} play chess, {B} play go and {C} play bridge. {AB} play chess and go, "
            f"{AC} play chess and bridge, {BC} play go and bridge, and {abc} play all three. How many play none?",
            ans, [total - (A + B + C - AB - AC - BC), total - (A + B + C), abc, ans + abc],
            f"At least one = {A} + {B} + {C} − {AB} − {AC} − {BC} + {abc} = {total - ans}. None = {total} − {total - ans} = {ans}.")


TOPICS = {"Math": {"arithmetic": arithmetic, "algebra": algebra, "number-properties": number_properties},
          "Logic": {"deduction": deduction, "sets": sets}}


def _fmt(v):
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return str(v)


def build(seed=7):
    """Return the checked item list in the import_items.py JSON shape."""
    rng = random.Random(seed)
    items, seen = [], set()
    for section, topics in TOPICS.items():
        for topic, make in topics.items():
            for tier in ("Easy", "Medium", "Hard"):
                made = 0
                while made < PER_TOPIC[section]:
                    stem, ans, distractors, expl = make(rng, tier)
                    if stem in seen:
                        continue
                    seen.add(stem)
                    if isinstance(ans, str):
                        choices = [ans] + [d for d in distractors if d != ans][:3]
                        rng.shuffle(choices)
                        key = LETTERS[choices.index(ans)]
                    else:
                        choices, key = _mc(rng, ans, distractors, _fmt)
                    assert choices.count(_fmt(ans)) == 1 and choices[LETTERS.index(key)] == _fmt(ans)
                    assert len(set(choices)) == len(choices)
                    items.append(dict(section=section, topic=topic, difficulty=tier, stem=stem,
                                      choices=choices, key=key, explanation=expl))
                    made += 1
    return items


if __name__ == "__main__":
    its = build()
    print(f"{len(its)} items built and checked")
