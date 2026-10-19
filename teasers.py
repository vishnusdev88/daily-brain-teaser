"""Daily brain-teaser generator.

Every answer is computed by code and cross-checked by brute force in selftest(),
so a wrong answer never gets posted. The same date always gives the same teaser.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field, asdict
from datetime import date
from fractions import Fraction


@dataclass
class Teaser:
    kind: str
    title: str            # short headline shown above the puzzle
    body: list            # one paragraph / line per entry
    answer: str           # goes in the comment
    explanation: str      # one-liner for the comment
    meta: dict = field(default_factory=dict)  # raw numbers, used by selftest()

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- generators

def sequence(rng):
    style = rng.choice(["add", "multiply", "squares", "fibonacci", "interleaved", "growing_gaps"])
    if style == "add":
        a, d = rng.randint(2, 20), rng.randint(3, 11)
        seq = [a + d * i for i in range(6)]
        why = f"Add {d} each time."
    elif style == "multiply":
        a, r = rng.randint(1, 5), rng.choice([2, 3])
        seq = [a * r ** i for i in range(6)]
        why = f"Multiply by {r} each time."
    elif style == "squares":
        k = rng.randint(1, 9)
        seq = [(i + 1) ** 2 + k for i in range(6)]
        why = f"Square numbers (1, 4, 9, 16...) plus {k}."
    elif style == "fibonacci":
        seq = [rng.randint(1, 6), rng.randint(2, 9)]
        while len(seq) < 6:
            seq.append(seq[-1] + seq[-2])
        why = "Each number is the sum of the two before it."
    elif style == "interleaved":
        a, b = rng.randint(1, 9), rng.randint(25, 45)
        da, db = rng.randint(2, 6), rng.randint(2, 7)
        seq = []
        for i in range(3):
            seq += [a + da * i, b - db * i]
        why = (f"Two patterns are mixed: the 1st, 3rd and 5th numbers go up by {da}; "
               f"the 2nd, 4th and 6th go down by {db}.")
    else:  # growing_gaps
        s, d = rng.randint(1, 10), rng.randint(1, 4)
        seq = [s]
        for i in range(5):
            seq.append(seq[-1] + d + i)
        why = f"The gaps grow by 1 each time: +{d}, +{d + 1}, +{d + 2}, ..."
    shown = ", ".join(map(str, seq[:5])) + ", ?"
    return Teaser("sequence", "What comes next?", [shown], str(seq[5]), why,
                  {"seq": seq, "style": style})


def symbols(rng):
    s, c, t = rng.sample(range(2, 16), 3)
    totals = [3 * s, s + 2 * c, c + 2 * t]
    body = [
        f"★ + ★ + ★ = {totals[0]}",
        f"★ + ● + ● = {totals[1]}",
        f"● + ■ + ■ = {totals[2]}",
        "★ + ● + ■ = ?",
    ]
    ans = s + c + t
    why = f"★ = {s}, ● = {c}, ■ = {t}, so {s} + {c} + {t} = {ans}."
    return Teaser("symbols", "Find the missing value", body, str(ans), why,
                  {"totals": totals})


PAIRS = [("ball", "bat"), ("pen", "diary"), ("pencil", "bag"), ("cap", "jacket"),
         ("cup of tea", "sandwich")]


def bat_and_ball(rng):
    a, b = rng.choice(PAIRS)
    k = rng.randint(1, 9)
    d = rng.choice([10, 20, 30, 40, 50, 100, 200])
    total = d + 2 * k
    body = [
        f"A {a} and a {b} cost ₹{total} together.",
        f"The {b} costs ₹{d} more than the {a}.",
        f"How much does the {a} cost?",
    ]
    why = (f"Not ₹{2 * k}! The {a} is ₹{k} and the {b} is ₹{k + d}, "
           f"which adds up to ₹{total}.")
    return Teaser("bat_and_ball", "Don't rush this one!", body, f"₹{k}", why,
                  {"total": total, "diff": d})


RULES = [  # (function, worked example, rule in words)
    (lambda a, b: a * b + a, lambda a, b: f"{a} × {b} + {a}", "first × second + first"),
    (lambda a, b: a * b + b, lambda a, b: f"{a} × {b} + {b}", "first × second + second"),
    (lambda a, b: a * a + b, lambda a, b: f"{a} × {a} + {b}", "first × first + second"),
    (lambda a, b: a * b - a, lambda a, b: f"{a} × {b} − {a}", "first × second − first"),
]


def trick_sums(rng):
    idx = rng.randrange(len(RULES))
    f, fmt, words = RULES[idx]
    gap = rng.randint(2, 4)
    rows = [(a, a + gap) for a in (1, 2, 3)]
    qa = rng.randint(6, 9)
    qb = qa + gap
    body = [f"{a} + {b} = {f(a, b)}" for a, b in rows] + [f"{qa} + {qb} = ?"]
    ans = f(qa, qb)
    why = f"The secret rule is: {words}. So {qa} + {qb} = {fmt(qa, qb)} = {ans}."
    return Teaser("trick_sums", "Crack the secret rule", body, str(ans), why,
                  {"rule": idx})


WORKERS = [("machines", "make", "toys"), ("chefs", "bake", "pizzas"),
           ("printers", "print", "posters"), ("painters", "paint", "walls")]


def machines(rng):
    n = rng.choice([3, 4, 5, 6, 8, 10])
    m = rng.choice([50, 100, 200, 500])
    who, verb, what = rng.choice(WORKERS)
    body = [f"If {n} {who} {verb} {n} {what} in {n} minutes, how many minutes "
            f"do {m} {who} need to {verb} {m} {what}?"]
    why = (f"Each of the {who} takes {n} minutes to finish one, so {m} {who} "
           f"working side by side also take {n} minutes.")
    return Teaser("machines", "Think before you answer", body, f"{n} minutes", why,
                  {"n": n, "m": m})


def lily_pads(rng):
    n = rng.randint(20, 60)
    body = [
        "A patch of lily pads doubles in size every day.",
        f"It covers the whole pond on day {n}.",
        "On which day was the pond HALF covered?",
    ]
    why = f"It doubles every day, so the day before it was full (day {n - 1}), it was half full."
    return Teaser("lily_pads", "Spot the trick", body, f"Day {n - 1}", why, {"n": n})


def handshakes(rng):
    n = rng.randint(5, 12)
    body = [
        f"{n} friends meet at a party.",
        "Everyone shakes hands with everyone else exactly once.",
        "How many handshakes in total?",
    ]
    ans = n * (n - 1) // 2
    why = (f"Each person shakes {n - 1} hands: {n} × {n - 1} = {n * (n - 1)}. "
           f"Every handshake is counted twice, so {ans}.")
    return Teaser("handshakes", "How many in total?", body, str(ans), why, {"n": n})


GENERATORS = [sequence, symbols, bat_and_ball, trick_sums, machines, lily_pads, handshakes]


def make_teaser(d: date) -> Teaser:
    rng = random.Random(d.toordinal())
    return GENERATORS[d.toordinal() % len(GENERATORS)](rng)


# ----------------------------------------------------------------- self-test

def _check(t: Teaser):
    m = t.meta
    if t.kind == "sequence":
        s, style = m["seq"], m["style"]
        assert len(s) == 6 and t.answer == str(s[5])
        diffs = [s[i + 1] - s[i] for i in range(5)]
        if style == "add":
            assert len(set(diffs)) == 1
        elif style == "multiply":
            assert len({Fraction(s[i + 1], s[i]) for i in range(5)}) == 1
        elif style == "squares":
            k = s[0] - 1
            assert all(s[i] == (i + 1) ** 2 + k for i in range(6))
        elif style == "fibonacci":
            assert all(s[i] == s[i - 1] + s[i - 2] for i in range(2, 6))
        elif style == "interleaved":
            odd, even = s[0::2], s[1::2]
            assert len({odd[i + 1] - odd[i] for i in range(2)}) == 1
            assert len({even[i + 1] - even[i] for i in range(2)}) == 1
            assert all(x > 0 for x in s)
        else:
            assert all(diffs[i + 1] - diffs[i] == 1 for i in range(4))
    elif t.kind == "symbols":
        e1, e2, e3 = m["totals"]
        sols = [(s, c, q) for s in range(1, 60) for c in range(1, 60) for q in range(1, 60)
                if 3 * s == e1 and s + 2 * c == e2 and c + 2 * q == e3]
        assert len(sols) == 1 and t.answer == str(sum(sols[0])), (sols, t.answer)
    elif t.kind == "bat_and_ball":
        sols = [p for p in range(0, m["total"] + 1) if p + (p + m["diff"]) == m["total"]]
        assert len(sols) == 1 and t.answer == f"₹{sols[0]}"
    elif t.kind == "trick_sums":
        f = RULES[m["rule"]][0]
        for line in t.body[:3]:
            lhs, c = line.split(" = ")
            a, b = (int(x) for x in lhs.split(" + "))
            assert f(a, b) == int(c)
        lhs = t.body[3].split(" = ")[0]
        a, b = (int(x) for x in lhs.split(" + "))
        assert str(f(a, b)) == t.answer
    elif t.kind == "machines":
        n, mm = m["n"], m["m"]
        rate = Fraction(1, n)                      # items per worker per minute
        assert Fraction(n) == n * rate * n          # n workers, n minutes -> n items
        assert t.answer == f"{Fraction(mm) / (mm * rate)} minutes".replace("/1", "")
    elif t.kind == "lily_pads":
        n = m["n"]
        area, half_day = 1, None
        for day in range(1, n + 1):
            if day > 1:
                area *= 2
            if half_day is None and area * 2 >= 2 ** (n - 1):
                half_day = day
        assert half_day == n - 1 and t.answer == f"Day {half_day}"
    elif t.kind == "handshakes":
        n = m["n"]
        assert t.answer == str(len(list(itertools.combinations(range(n), 2))))
    else:
        raise AssertionError(f"unknown kind {t.kind}")


def selftest(days: int = 800):
    start = date(2026, 1, 1).toordinal()
    counts = {}
    for i in range(days):
        t = make_teaser(date.fromordinal(start + i))
        _check(t)
        counts[t.kind] = counts.get(t.kind, 0) + 1
    print(f"selftest OK: {days} days, all answers verified")
    for k, v in sorted(counts.items()):
        print(f"  {k:14s} {v}")


if __name__ == "__main__":
    selftest()
    print()
    for i in range(7):
        t = make_teaser(date(2026, 10, 18 + i))
        print(f"[{t.kind}] {t.title}")
        for line in t.body:
            print("   ", line)
        print("    ->", t.answer, "|", t.explanation)
        print()
