"""Sanity-checks the golden set BEFORE we ever call a model.

Every gold query must (a) run without error and (b) return something you can
eyeball as correct. A wrong label is worse than no label — it silently caps
your accuracy and you'll blame the model.

    python db/verify_golden.py
"""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "store.db"
GOLDEN = ROOT / "data" / "golden.jsonl"


def main() -> None:
    con = sqlite3.connect(DB)
    for line in GOLDEN.read_text().strip().splitlines():
        item = json.loads(line)
        rows = con.execute(item["gold_sql"]).fetchall()
        flag = "  [order matters]" if item["order_matters"] else ""
        print(f"\nQ{item['id']}: {item['question']}{flag}")
        print(f"  -> {rows}")
        if not rows:
            print("  !! EMPTY RESULT — a question nobody can get right is a bad test")
    con.close()


if __name__ == "__main__":
    main()
