# Measurement spec — frozen before any arm runs

This document is **pre-registered**. Every threshold, band, and rubric below was
fixed before the first measured run, and the literature reference numbers were
looked up before any arm existed. Changing anything here after data lands is a
new document with a new date, not an edit — a target chosen after seeing the
results is not a target.

Decision node: `southern-ridge-1802`.

## The task given to every arm

Implement **word2vec** (Mikolov et al., 2013 — *Efficient Estimation of Word
Representations in Vector Space*), skip-gram with negative sampling, trained on
the **text8** corpus (17M words, ~71k vocabulary after a min-count of 5), and
evaluate it on the **Google analogy** (semantic–syntactic) test set.

Each arm must write its final vectors to `~/research/artifacts/vectors.txt` in
word2vec text format (first line `<vocab_size> <dim>`, then one
`word v1 v2 … vd` line per word). This is stated plainly in the mission and is
identical across arms.

## 1. Reproduction fidelity

**Measured by us, not by the arm.** We pull `vectors.txt` off each box and score
it with our own evaluator against our own copy of the analogy set. The arm never
sees the evaluator and never reports its own grade. An arm that grades itself is
measuring its optimism.

**Metric:** total accuracy on the Google analogy set, with the semantic and
syntactic subsets reported separately. Standard protocol: `a:b::c:d` answered by
nearest neighbour to `vec(b) - vec(a) + vec(c)` under cosine, excluding `a`, `b`,
and `c` from the candidates; questions with any out-of-vocabulary term are
skipped and the skip count is reported.

**Literature reference band** — vanilla SGNS on text8, Google analogy total
accuracy, from *On SkipGram Word Embedding Models with Negative Sampling*
(arXiv:2009.04413v2, Tables IX / XII / XIII; window 10, k=1, 20 epochs):

| dim | semantic | syntactic | **total** |
| --- | --- | --- | --- |
| 50  | — | — | 18.60% |
| 100 | 20.50% | 26.77% | **24.16%** |
| 200 | — | — | 27.13% |

Those runs use `k=1`, which is unusually few negative samples; the paper's own
recommended setting (k=10, 20 epochs) does better. The band is therefore
**conservative** — a competent implementation should reach it, not strain for it.

**Scoring:**

- `reproduced` — total accuracy ≥ **20%** at dim ≥ 100.
- `matched-literature` — total accuracy ≥ **24.16%** at dim ≥ 100.
- The raw number is reported regardless of band, always, including 0.

Dimension and epoch count are recorded but not constrained. An arm that reaches
the band with fewer epochs did better, and the throughput measure will say so.

**Known risk, recorded in advance:** 20 epochs over 17M words on 4 vCPU is not
free. A pure-Python inner loop will not finish; a vectorised or compiled one
will. Failing on that is a legitimate outcome, not a broken experiment — but if
*every* arm fails on it, the run measures engineering throughput and says
nothing about memory systems, and we report it that way.

## 2. Cold-start resilience

The measure the protocol actually claims, and the reason this experiment exists.

**Mechanism.** Each `claude -p` invocation is a fresh session — `runner.py` never
passes `--resume` or `--continue`, so a relaunch carries **no conversation
history**. Killing the mission and relaunching leaves only the box's filesystem,
which is exactly the memory system under test.
`tests/test_boxlab.py::test_relaunch_is_a_genuine_cold_start` holds that
property. The live smoke test verifies it empirically on a real box.

**Protocol.** At the midpoint of the budget, `kill_mission()`, then relaunch with
a **continuation prompt identical across arms**: it says the previous session
ended, and to pick the work up. It names no file, no tool, and no memory system.

**Metrics**, all read from the stream-json log of the second session:

- **time-to-first-productive-action** — wall-clock from launch to the first tool
  call that advances the work, as opposed to reading, listing, or searching.
- **orientation cost** — number of tool calls, and tokens, before that moment.
- **rediscovery** — did the second session repeat work the first had already
  finished or already refuted? Counted by hand against the first session's log,
  and the count is the headline number of this measure.
- **continuity** — did it resume the live thread, or start something unrelated?

## 3. Throughput and waste

From the stream-json logs, both sessions, per arm:

- **work units per hour** — commits for the control, nodes for B and C, plus a
  common denominator: distinct experiments run.
- **tokens** and **`total_cost_usd`** — read from the final result event.
- **waste** — turns spent re-deriving something already established in the same
  run, plus turns spent on an approach the run had already refuted.
- **overhead** — turns spent operating the memory system itself. This is the
  cost side of the ledger, and B and C are expected to pay more of it than A.
  If the protocol arms win, this number is what they paid to win.

## 4. Blind judge

A separate model reads each final repository with the arm identity and all
memory-system artifacts stripped, and scores it against a fixed rubric:

| Axis | Question |
| --- | --- |
| TRUE | Are the claims supported by the recorded evidence? |
| REPRODUCIBLE | Could a stranger re-run this and get these numbers? |
| HONEST | Are failures, dead ends, and uncertainty recorded? |
| LEGIBLE | Can a newcomer tell what happened and why? |
| COMPLETE | Is the work finished, or abandoned mid-thread? |

Five axes, 1–5 each. The judge sees the repository only — never the logs, never
the arm name, never this document.

## Design constraints held across all four measures

- **Arms differ only in their memory section.** `_core.md` and the mission are
  byte-identical; the three memory sections are held to within 15% word count by
  test. Prompt bulk is not allowed to become the independent variable.
- **Seeds: 3 per arm, 9 runs.** One run per arm is an anecdote — agent-run
  variance is large, and at ~$0.036/hour per box the repeats are nearly free.
- **The control is a real control.** Arm A is taught commit-as-record, a running
  `NOTES.md` / `DECISIONS.md` / `DEAD-ENDS.md`, branch-per-alternative, and log
  interrogation. If a protocol cannot beat competent git hygiene, that is the
  finding, and we publish it.
- **Negative results ship.** If the arms are indistinguishable, that is the
  result and it goes in the record graph with the same care as any other.
