"""Re-grade saved predictions without calling the model again.

Generation and grading are separate steps on purpose. The model's output is
data; the scorer is code that keeps changing as you find its blind spots. When
you fix the scorer you want the new numbers immediately — not another 60s of
inference, and not a comparison muddied by the model having answered slightly
differently the second time.

Reads results/*.csv (written by run_eval.py) and re-scores every saved query.

    python rescore.py
"""

import csv
import json
from pathlib import Path

from run_eval import RESULTS, GOLDEN, MODEL, print_leaderboard
from score import score_one


def main() -> None:
    golden = {item["id"]: item for item in
              (json.loads(l) for l in GOLDEN.read_text().strip().splitlines())}

    files = sorted(RESULTS.glob("*.csv"))
    if not files:
        raise SystemExit("no results/*.csv yet — run run_eval.py first")

    summaries = []
    for path in files:
        rows = list(csv.DictReader(path.open()))
        correct = subset = 0
        rescored = []

        print(f"\n=== {path.stem} ===")
        for row in rows:
            item = golden[int(row["id"])]
            r = score_one(row["predicted_sql"], item["gold_sql"], item["order_matters"])
            correct += r["strict"]
            subset += r["subset"]

            mark = "PASS" if r["strict"] else ("~sub" if r["subset"] else "FAIL")
            print(f"  Q{row['id']:>2} {mark}  {item['question'][:52]}")
            if not r["strict"]:
                print(f"        {r['reason'][:100]}")

            row.update(strict=r["strict"], subset=r["subset"], reason=r["reason"])
            rescored.append(row)

        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rescored[0]))
            w.writeheader()
            w.writerows(rescored)

        summaries.append({
            "prompt": path.stem, "correct": correct, "subset": subset,
            "total": len(rows), "accuracy": correct / len(rows),
            "subset_accuracy": subset / len(rows),
        })

    print_leaderboard(summaries, summaries[0]["total"], f"{MODEL}, rescored")


if __name__ == "__main__":
    main()
