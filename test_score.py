"""Proof that the grader works, before any model is involved.

If you don't trust the scorer, you can't trust the leaderboard. So we hand it
queries whose verdict we already know — including the cases that are easy to
get wrong: same answer written differently, and right answer with extra
columns attached.

    python test_score.py
"""

from score import score_one

Q_ATL = "SELECT name FROM customers WHERE city = 'Atlanta'"

CASES = [
    # (name, predicted_sql, gold_sql, order_matters, expect_strict, expect_subset)
    ("identical query",
     "SELECT COUNT(*) FROM customers", "SELECT COUNT(*) FROM customers", False, True, True),

    ("different SQL, same answer",
     Q_ATL, "SELECT name FROM customers WHERE 'Atlanta' = city", False, True, True),

    ("different row order, order doesn't matter",
     Q_ATL + " ORDER BY name DESC", Q_ATL + " ORDER BY name ASC", False, True, True),

    ("different row order, order DOES matter",
     "SELECT city FROM customers GROUP BY city ORDER BY COUNT(*) ASC",
     "SELECT city FROM customers GROUP BY city ORDER BY COUNT(*) DESC", True, False, False),

    ("int vs float — 4 and 4.0 are the same answer",
     "SELECT SUM(1.0) FROM customers WHERE city='Atlanta'",
     "SELECT COUNT(*) FROM customers WHERE city='Atlanta'", False, True, True),

    ("extra column — strict fails, subset passes",
     "SELECT name, price FROM products ORDER BY price DESC LIMIT 1",
     "SELECT name FROM products ORDER BY price DESC LIMIT 1", False, False, True),

    ("SELECT * — strict fails, subset passes",
     "SELECT * FROM customers WHERE city = 'Atlanta'", Q_ATL, False, False, True),

    ("missing a column the question asked for",
     "SELECT category FROM products GROUP BY category",
     "SELECT category, COUNT(*) FROM products GROUP BY category", False, False, False),

    ("right shape, wrong rows",
     "SELECT name FROM customers WHERE city = 'Chicago'", Q_ATL, False, False, False),

    ("extra column AND wrong row count",
     "SELECT name, price FROM products ORDER BY price DESC",
     "SELECT name FROM products ORDER BY price DESC LIMIT 1", False, False, False),

    ("genuinely wrong answer",
     "SELECT name FROM customers WHERE city = 'Chicago'", Q_ATL, False, False, False),

    ("query that crashes",
     "SELECT nope FROM customers", "SELECT COUNT(*) FROM customers", False, False, False),

    ("model returned nothing",
     "", "SELECT COUNT(*) FROM customers", False, False, False),

    ("empty result is never a match",
     "SELECT name FROM customers WHERE city = 'Mars'", Q_ATL, False, False, False),
]


def main() -> None:
    failures = 0
    for name, pred, gold, order_matters, exp_strict, exp_subset in CASES:
        r = score_one(pred, gold, order_matters)
        ok = r["strict"] == exp_strict and r["subset"] == exp_subset
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"        strict={r['strict']} subset={r['subset']} "
              f"(expected {exp_strict}/{exp_subset}) — {r['reason'][:70]}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} scorer tests passed")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
