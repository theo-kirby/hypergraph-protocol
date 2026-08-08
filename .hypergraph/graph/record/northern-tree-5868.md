---
node_id: adf562b9-3f78-5814-89ce-c717acb58b1a
slug: northern-tree-5868
title: 'Pilot: agent capability confirmed; self-grading bias measured; three harness defects fixed'
created_at: '2026-08-08T20:58:47+00:00'
parents:
- scarlet-orchard-8774
summary: ''
---
## What

Ran a 27-minute single-box pilot (arm A, git-only control) before committing to
the measured run, then launched the full experiment: 9 boxes, three arms, three
seeds, 2 hours each with the cold-start cut at 1 hour.

The pilot's purpose was to answer one question — can DeepSeek V4 Pro under pi
sustain real agentic work on this task? — and it answered four more, three of
them defects that would each have cost the whole run.

## Why

Every prior proof used a 2-turn smoke mission. Nothing had shown the agent could
download a corpus, write a trainer, debug it, and evaluate — nor that the
harvest and analysis path worked on a real workload. Operator chose a short pilot
over launching nine blind.

## Method

`lab.py run --arms git --seeds 1 --hours 0.45 --coldstart-frac 0.99`, one box
(`bx_5nd7cpyd`), budget-gated at $5. Afterwards the box was resumed to re-harvest
with the repaired code, then stopped.

Fidelity was scored twice on the **same** `vectors.txt`: once by the agent's own
evaluator (its `results.json`) and once by `research/eval/analogy.py`, which the
arm never sees.

## Result

**Capability: confirmed, decisively.** Within ~7 minutes the agent had downloaded
text8 (100 MB) and the analogy set, written `vocab.py` / `train.py` /
`evaluate.py`, and — reading the mission's warning that a pure-Python inner loop
would not finish — authored a **Cython extension** (`w2v_core.pyx` → `.c` →
compiled `.so`) and was training on it at 100% CPU. In 27 minutes it produced a
complete `vectors.txt` (71,290 words, dim 100) and a `results.json`.

**Self-grading bias, measured.** The agent and our evaluator disagree on the same
vectors:

| | agent's `results.json` | our evaluator |
| --- | --- | --- |
| total accuracy | **21.47%** | **19.36%** |
| questions answered | 9,310 | **17,827** |
| skipped (OOV) | **10,234 (52%)** | 1,717 (9%) |
| semantic answered | 420 | **7,416** |
| semantic accuracy | 43.81% | 13.89% |

Same file, same 71,290-word vocabulary. The agent's evaluator silently discarded
**more than half the test set** — almost all of the semantic questions, which are
the hard ones — and reported a flattering figure over the survivors. It was not
dishonest; its evaluation had a bug it could not see. This is exactly what
METRICS.md pre-registered against, confirmed on the first real run, and it makes
independent scoring load-bearing rather than fastidious.

**The pre-registered target is well calibrated:** 19.36% in 27 minutes at 3
epochs, against a 20% `reproduced` band and a 24.16% literature reference.
Reachable in the real run, not free.

**Three harness defects, each fatal to a run, each invisible without the pilot:**

1. **Harvest failed** — `binascii: Incorrect padding`. `ssh_exec` returns stdout
   followed by stderr, so the ssh host-key banner lands *after* the base64 blob;
   the code stripped only a leading banner. Fixed by sentinel-framing both ends,
   the same pattern already used for log fetches. Re-harvest succeeded: 28.5 MB.
2. **A failed harvest still reported `complete`.** `ok` was set unconditionally.
   That is the dangerous shape: the failure surfaces at analysis, by which point
   the box is gone and the evidence with it. `ok` now tracks the harvest and the
   note says `HARVEST FAILED` at teardown.
3. **The spend guard was reading a field that does not track spend.** Across the
   pilot the key's own `usage` moved **$0.02** while the account's `total_usage`
   moved **$0.82** — a 40× understatement. A guard on the key field would have
   reported ~0% of budget consumed the entire way and never tripped. It now reads
   account usage.

A fourth, smaller correction: `vectors.txt` is ~68 MB, so pulling it as a second
base64 text transfer duplicated what the tarball already gzips. It is now probed
for existence and travels inside the archive.

**The measured run is launched** — 9 boxes, `--hours 2 --coldstart-frac 0.5`,
budget gate $40. Two hours rather than three on Operator decision, after the cost
data: $0.82 per 27-minute run by account delta extrapolates to roughly $27–49 for
nine 3-hour runs against ~$49.84 available. The pilot makes 2 hours defensible on
its own terms — it produced a trained model and an evaluation in 27 minutes, so
each phase gets roughly twice that.

Stated plainly because it bounds what the guard can do: with nine simultaneous
launches the budget gate fires nine times inside ~72 seconds, before anything has
spent. It protects a staggered run, not this one. Accepted deliberately.

Tests: 107 pass. Checker: 0 violations. No boxes left running at any point.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e82898940ce43e09d0406dfcd05aed74a0d38cee

## State Impact

- target: protocol-benchmark-4417 — pilot passed and the measured run is launched (9 boxes, 3 arms x 3 seeds, 2h each, cold-start cut at 1h, budget gate $40). Capability confirmed decisively: in 27 minutes the agent wrote a Cython extension and produced a complete 71,290-word vectors.txt scoring 19.36%, against a 20% reproduced band and 24.16% literature reference — so the pre-registered target is reachable but not free. Three harness defects found and fixed (harvest base64 framing, a failed harvest reporting complete, and a spend guard reading a field that understated real spend 40x). Two hours per run rather than three, on Operator decision after the cost data.
- target: protocol-benchmark-4417 — negative knowledge, measured rather than assumed: an agent's self-reported score is not a score. On identical vectors the agent claimed 21.47% while our evaluator measured 19.36%, because its evaluation silently discarded 10,234 of 19,544 questions (52%) against our 1,717 (9%) — almost the entire semantic subset, which is the hard one. Independent scoring is load-bearing for measure 1, not fastidiousness.
- target: empty-forest-6305 — negative knowledge for anyone reading command output over ssh in this codebase: BoxController.ssh_exec returns stdout followed by stderr, so an ssh host-key banner lands AFTER the payload, not before. Prefix-stripping a base64 blob therefore leaves trailing junk and fails with 'Incorrect padding'. Sentinel-frame both ends of any binary or structured payload.
