"""The runner: every prompt x every question -> a leaderboard.

    python run_eval.py                 # all prompts in prompts/
    python run_eval.py v3_schema_rules # just one

For each (prompt, question) pair it asks the model for SQL, runs that SQL
against the database, and compares rows to the hand-labeled gold query. The
number it prints at the end is execution accuracy: what fraction of questions
the prompt got right.
"""

import csv
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import ollama

from score import score_one

ROOT = Path(__file__).resolve().parent
DB = ROOT / "db" / "store.db"
GOLDEN = ROOT / "data" / "golden.jsonl"
PROMPTS = ROOT / "prompts"
RESULTS = ROOT / "results"

MODEL = "llama3.2"


def load_schema() -> str:
    """Read the real CREATE TABLE statements straight out of the database.

    Better than typing the schema into the prompt by hand: it can never drift
    out of sync with the database the queries actually run against.
    """
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    con.close()
    return "\n".join(r[0] for r in rows)


def load_golden() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text().strip().splitlines()]


def extract_sql(text: str) -> str:
    """Pull the SQL out of whatever the model wrapped it in.

    Models love to add ```sql fences and a paragraph of explanation. That's a
    formatting problem, not a SQL problem, so we strip it rather than marking
    the answer wrong — the prompt's job is to stop it happening at all.
    """
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1)

    # Keep from the first SELECT/WITH to the end of that statement.
    start = re.search(r"\b(SELECT|WITH)\b", text, re.I)
    if not start:
        return ""
    text = text[start.start():]
    return text.split(";")[0].strip()


def ask_model(prompt: str) -> str:
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        # Temperature 0: same question -> same answer. Without this your
        # accuracy wobbles run to run and you can't tell a real prompt
        # improvement from luck.
        options={"temperature": 0},
    )
    return resp["message"]["content"]


def run_prompt(prompt_file: Path, golden: list[dict], schema: str) -> dict:
    template = prompt_file.read_text()
    rows, correct, subset = [], 0, 0
    t0 = time.time()

    print(f"\n=== {prompt_file.stem} ===")
    for item in golden:
        prompt = template.format(question=item["question"], schema=schema)
        raw = ask_model(prompt)
        pred_sql = extract_sql(raw)
        r = score_one(pred_sql, item["gold_sql"], item["order_matters"])
        correct += r["strict"]
        subset += r["subset"]

        mark = "PASS" if r["strict"] else ("~sub" if r["subset"] else "FAIL")
        print(f"  Q{item['id']:>2} {mark}  {item['question'][:52]}")
        if not r["strict"]:
            print(f"        {r['reason'][:100]}")

        rows.append({
            "id": item["id"], "question": item["question"],
            "predicted_sql": pred_sql, "gold_sql": item["gold_sql"],
            "strict": r["strict"], "subset": r["subset"], "reason": r["reason"],
        })

    elapsed = time.time() - t0
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{prompt_file.stem}.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    acc, sub_acc = correct / len(golden), subset / len(golden)
    print(f"  strict {correct}/{len(golden)} = {acc:.0%}   "
          f"subset {subset}/{len(golden)} = {sub_acc:.0%}   "
          f"({elapsed:.0f}s)  -> {out.name}")
    return {"prompt": prompt_file.stem, "correct": correct, "subset": subset,
            "total": len(golden), "accuracy": acc, "subset_accuracy": sub_acc,
            "seconds": elapsed}


def print_leaderboard(results: list[dict], n: int, note: str) -> None:
    """Strict and subset side by side.

    The gap between the two columns is the interesting part: it is the share of
    questions the model actually understood but formatted wrong.
    """
    print("\n" + "=" * 68)
    print(f"LEADERBOARD  ({note}, {n} questions)")
    print("=" * 68)
    print(f"  {'prompt':<20} {'strict':>7} {'subset':>7}   {'gap':>4}")
    print("  " + "-" * 64)
    for r in sorted(results, key=lambda r: (-r["accuracy"], -r["subset_accuracy"])):
        bar = "#" * round(r["accuracy"] * 20)
        gap = r["subset"] - r["correct"]
        print(f"  {r['prompt']:<20} {r['accuracy']:>6.0%} {r['subset_accuracy']:>7.0%}   "
              f"{('+' + str(gap)) if gap else '  -':>4}  {bar}")
    print("\n  strict = exact table match   subset = gold answer present, extra columns allowed")
    print("  gap    = questions understood but formatted wrong")


def main() -> None:
    golden = load_golden()
    schema = load_schema()

    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(PROMPTS.glob("*.txt"))
    if wanted:
        files = [f for f in files if wanted in f.stem]
    if not files:
        sys.exit(f"no prompt files matched {wanted!r}")

    results = [run_prompt(f, golden, schema) for f in files]

    print_leaderboard(results, len(golden), f"{MODEL}, temperature 0")


if __name__ == "__main__":
    main()
