# evalkit — a text-to-SQL evaluation harness

Most prompt engineering is guesswork: change some wording, eyeball two examples,
declare victory. This is a small harness that replaces the guessing with a
number.

It asks a local LLM to turn plain-English questions into SQL, **runs** the
generated SQL against a real database, and compares the returned rows to a
hand-labeled answer key. Then it ranks prompts on a leaderboard.

Runs entirely locally on Ollama. No API keys, no cost.

## The headline result

Three prompts, same model (`llama3.2`), same 10 questions, temperature 0:

```
LEADERBOARD  (llama3.2, 10 questions, temperature 0)
  prompt                strict  subset    gap
  ----------------------------------------------------------
  v2_schema               60%     90%     +3   ############
  v1_naive                20%     40%     +2   ####
  v3_schema_rules         20%     40%     +2   ####
```

`v3` is the prompt everyone's instinct says should win — it has the schema,
explicit output rules, and a few-shot example. It scored **the same as giving
the model no schema at all**, because the example's format nudged it into
inventing `T1`/`T2` table aliases that don't exist in the database.

That result is the reason this repo exists. Without measurement, `v3` ships.

## Two numbers, not one

`strict` demands an exact table match. `subset` still counts the answer if the
prediction *contains* the gold result but drags extra columns along — asked for
the product name, returned `('Espresso Machine', 499.0)`.

The gap between them is the whole diagnostic. `v2` scores 60% strict and 90%
subset: three of its four failures were correct answers formatted wrong, and
only **one** was a real reasoning error (it forgot `LIMIT 1` and returned every
product instead of the top one).

Those two readings imply completely different work. At 60% you go rewrite the
prompt's reasoning guidance. At "90% with a formatting gap" you add one line
about returning only the requested columns, and you are near the ceiling. A
single accuracy number hides which situation you are in.

The split is borrowed from IBM's
[text2sql-eval-toolkit](https://github.com/IBM/text2sql-eval-toolkit), whose
`subset_non_empty_execution_accuracy` exists for exactly this reason: strict
graders "expect exact column sets, even when the question allows flexibility."

## How it's scored: execution accuracy

Comparing generated SQL to reference SQL as *text* is a bad grader —
`WHERE age > 30` and `WHERE 30 < age` are the same query and would be marked
different. So instead:

1. Run the model's SQL against the database.
2. Run the hand-written gold SQL against the same database.
3. Compare the rows that come back.

**The database is the judge.** No LLM-as-judge, no fuzzy string matching,
nothing to argue with. This is the standard used by benchmarks like Spider.

Two rules keep it honest:

- **Row order is ignored** unless the question actually asks for an ordering.
  Each golden item carries an `order_matters` flag; `"list the cities, highest
  first"` is order-sensitive, `"list customers in Atlanta"` is not.
- **A query that crashes is wrong.** No partial credit for SQL that references
  a column that doesn't exist.
- **An empty result never matches.** Returning nothing shouldn't be rewarded,
  even when the gold result is also empty.
- **`4` and `4.0` are the same answer.** `COUNT` returns an int and `SUM`
  returns a float; comparing them as raw strings fails correct queries over a
  type detail nobody asked about. Every cell is canonicalized first.

## The golden set is the real work

`data/golden.jsonl` holds 10 questions, each with SQL written and verified by
hand. `db/verify_golden.py` checks every gold query *before* any model is
called — and it caught two bugs in the answer key on the first run:

- **A question with an empty answer.** "List customers who have never placed an
  order" returned nothing, because every customer happened to have one. A test
  nobody can fail is not a test. Fixed by adding an order-less customer.
- **A tie in an order-sensitive question.** Two cities were tied on customer
  count, so the "correct" ordering was whatever SQLite felt like that day — a
  flaky test that would randomly fail a correct model. Fixed by breaking the tie
  in the data.

A wrong label is worse than no label: it silently caps your accuracy, and you
spend the afternoon blaming the model.

Likewise `test_score.py` proves the *grader* works before it grades anything —
7 cases including "different SQL, same answer" (must pass) and "right rows,
wrong order, order matters" (must fail).

## What the failures actually are

Reading `results/*.csv` — which is the point of saving them — the misses split
into two very different piles:

| Failure | Example | Real problem? |
|---|---|---|
| Extra columns | asked for the product name, returned `('Espresso Machine', 499.0)` | No — caught by subset match. Formatting. |
| Hallucinated schema | `no such column: o.total_amount` | Yes. The model invented a column. |
| Missing `LIMIT 1` | returned all 6 products ranked, not the top one | Yes. Misread the question. |
| Missing `DISTINCT` | `('Ava Patel',), ('Ava Patel',)` | Yes. Real SQL bug. |

**Three of four** of `v2`'s failures are the first kind — right rows, extra
columns — which is why its subset score is 90%. Only Q8 is a real miss.

The contrast with `v1` is just as sharp: 6 of its 8 failures are
`no such column` — with no schema in the prompt, it invents `total_amount`,
`CustomerID`, a `categories` table. Same model, same questions, completely
different failure mode.

## Layout

```
db/build_db.py       # builds store.db — 4 tables, ~30 rows, small enough to verify by hand
db/verify_golden.py  # sanity-checks the answer key before any model runs
data/golden.jsonl    # the 10 questions + hand-written gold SQL
prompts/*.txt        # the prompt variants being compared
score.py             # execution accuracy — runs both queries, compares rows
test_score.py        # tests for the grader itself
run_eval.py          # runs every prompt x every question, prints the leaderboard
results/*.csv        # per-question output: predicted SQL, verdict, reason
```

## Running it

Needs [Ollama](https://ollama.com) with `llama3.2` pulled.

```bash
ollama serve                       # in another terminal
ollama pull llama3.2
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python db/build_db.py
./venv/bin/python db/verify_golden.py   # confirm the answer key
./venv/bin/python test_score.py         # confirm the grader
./venv/bin/python run_eval.py           # run everything
./venv/bin/python run_eval.py v2        # or just one prompt
./venv/bin/python rescore.py            # re-grade saved output after a scorer change
```

Add a prompt by dropping a `.txt` file in `prompts/` with `{schema}` and
`{question}` placeholders. It joins the leaderboard automatically.

## Notes on methodology

- **Temperature 0.** Otherwise accuracy wobbles between runs and you can't tell
  a real improvement from luck.
- **Generation and grading are separate steps.** The scorer keeps changing as
  you find its blind spots; `rescore.py` re-grades saved predictions instantly,
  so a scorer fix isn't confounded by the model answering differently the second
  time.
- **Schema is read from the database at runtime**, not pasted into the prompt,
  so it can't drift from the database the queries actually run against.
- **10 questions is small.** One question is worth 10 percentage points, so
  differences under ~20 points here aren't meaningful. Scaling the golden set is
  the next step.

## Next

- [ ] Grow the golden set to ~50 questions so the numbers can be trusted
- [ ] Fix the extra-column failures in a `v4` prompt and close the strict/subset gap
- [ ] Add a second model to compare models, not just prompts
- [ ] Break accuracy down by question difficulty (single-table vs multi-join)
- [ ] Support multiple gold SQLs per question — some questions have several
      correct formulations (another idea from the IBM toolkit)

## License

MIT
