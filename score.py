"""Execution accuracy: the grader for text-to-SQL.

We do NOT compare SQL text. Two queries that look nothing alike can be equally
correct. Instead we RUN both against the database and compare the rows they
return. The database is the judge — no LLM, no fuzzy matching, no arguing.

Two metrics, reported side by side (the split is borrowed from IBM's
text2sql-eval-toolkit):

  strict — the returned table must match the gold table exactly.
  subset — the prediction still counts if it CONTAINS the gold answer but
           carries extra columns along with it.

Why both: a model that answers "which product is most expensive?" with
("Espresso Machine", 499.0) understood the question perfectly and formatted it
wrong. Strict says 0, subset says 1. The gap between the two numbers tells you
how much of your error is formatting versus real reasoning failure — and those
have completely different fixes.

Three rules keep it fair:
  * Row order is ignored unless the question asks for an ordering.
  * A query that crashes is wrong; it never gets to compare rows.
  * An empty result never counts as a match, even against an empty gold — a
    model returning nothing shouldn't be rewarded for it.
"""

import math
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "db" / "store.db"


def run_sql(sql: str) -> tuple[list | None, str | None]:
    """Execute `sql` read-only. Returns (rows, error) — exactly one is None."""
    # A fresh connection per query so one bad query can't poison the next.
    con = sqlite3.connect(DB)
    try:
        rows = con.execute(sql).fetchall()
        return rows, None
    except sqlite3.Error as e:
        # Any SQL error (bad column, syntax, wrong table) counts as a wrong answer.
        return None, str(e)
    finally:
        con.close()


def canonical(value) -> str:
    """Collapse a cell to a comparable string.

    The important case: SQLite hands back 4 from COUNT and 4.0 from SUM. They
    are the same answer, so 4.0 must canonicalize to "4" — otherwise the grader
    fails correct queries over a type detail nobody asked about.
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    if isinstance(value, int):
        return str(value)

    # Numeric-looking strings get the same treatment ("4.0" -> "4").
    text = str(value).strip()
    try:
        return canonical(float(text))
    except ValueError:
        return text


def normalize(rows: list, order_matters: bool) -> list:
    """Put rows in a comparable shape: canonical cells, sorted unless ordered."""
    shaped = [tuple(canonical(v) for v in row) for row in rows]
    return shaped if order_matters else sorted(shaped)


def is_subset_match(pred_rows: list, gold_rows: list, order_matters: bool) -> bool:
    """True if the prediction contains the gold answer, extra columns and all.

    Same number of rows is required — a prediction with the wrong rows is wrong
    no matter what columns it has. Within each row we ignore column order and
    just ask: is every gold value present in the predicted row?
    """
    if not pred_rows or not gold_rows:
        return False
    if len(pred_rows) != len(gold_rows):
        return False
    if len(pred_rows[0]) < len(gold_rows[0]):
        return False  # prediction has FEWER columns — it's missing something

    pred = normalize(pred_rows, order_matters)
    gold = normalize(gold_rows, order_matters)

    for p_row, g_row in zip(pred, gold):
        remaining = list(p_row)
        for value in g_row:
            if value not in remaining:
                return False
            remaining.remove(value)  # each gold value needs its own cell
    return True


def score_one(pred_sql: str, gold_sql: str, order_matters: bool) -> dict:
    """Grade one predicted query.

    Returns {"strict": bool, "subset": bool, "reason": str}. `subset` is always
    true when `strict` is — a exact match trivially contains the gold answer.
    """
    fail = lambda why: {"strict": False, "subset": False, "reason": why}

    if not pred_sql.strip():
        return fail("no SQL produced")

    pred_rows, err = run_sql(pred_sql)
    if err:
        return fail(f"query failed: {err}")

    gold_rows, gold_err = run_sql(gold_sql)
    if gold_err:  # our own label is broken — loud, not silent
        raise RuntimeError(f"GOLD QUERY IS BROKEN: {gold_err}")

    if not pred_rows:
        return fail("empty result")

    if normalize(pred_rows, order_matters) == normalize(gold_rows, order_matters):
        return {"strict": True, "subset": True, "reason": "match"}

    if is_subset_match(pred_rows, gold_rows, order_matters):
        extra = len(pred_rows[0]) - len(gold_rows[0])
        return {"strict": False, "subset": True,
                "reason": f"subset match ({extra} extra column(s)): got {pred_rows[:2]}"}

    return {"strict": False, "subset": False,
            "reason": f"wrong rows: got {pred_rows[:3]} want {gold_rows[:3]}"}
