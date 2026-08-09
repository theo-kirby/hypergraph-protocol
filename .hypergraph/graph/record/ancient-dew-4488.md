---
node_id: 959b81dc-777b-5c84-89d8-cd00c8cdd22c
slug: ancient-dew-4488
title: 'M5: nine runs complete — no detectable difference at n=3; control produced no usable model'
created_at: '2026-08-08T23:13:13+00:00'
parents:
- northern-tree-5868
summary: ''
flywheel:
  node_id: dfcc9df3-5a3b-581e-bd56-95f77bea2f55
  slug: hidden-star-2482
  revision: 0
  pushed_at: '2026-08-09T10:16:22+00:00'
  content_sha256: dfee72b1bed939540bd34e2f3711a5dbea77005113ef4fde3673344728da0746
---
## What

Ran the measured experiment to completion — 9 boxes, three arms, three seeds, 2
hours each with the cold-start cut at 1 hour — recovered it after the driver was
killed mid-run, scored every arm with the frozen evaluator, and found three
analysis defects that would each have produced a wrong published result.

## Why

Follows `northern-tree-5868`. This is the run the whole thrust exists to produce:
the first evidence distinguishing the protocol from plain git, rather than
showing only that it holds together.

## Method

`lab.py run --arms git flywheel hypergraph --seeds 3 --hours 2
--coldstart-frac 0.5 --harness pi --budget 40`. All nine launched clean, no
provisioning or launch failures.

**The driver died ten minutes in** — a caller-side 10-minute timeout on a
two-hour job, an operator error. The agents survived it: they launch
`nohup setsid` and never noticed. What did not survive was the schedule, which
lived only in the driver's memory. `boxlab/attach.py` rebuilt it from the dead
driver's log (box ids + phase-1 launch times) and carried each run to teardown on
**its own original clock**, so no arm's working period changed. The replacement
driver was daemonized (`os.fork` + `os.setsid`) so no caller timeout could reach
it. All nine were cut within ~90 seconds of their own one-hour mark; nine of nine
harvested; zero boxes left running.

Fidelity was scored by `research/eval/analogy.py` over each harvested
`vectors.txt` — never the arms' self-reports.

## Result

**Fidelity** (Google analogy, 19,544 questions, scored by us):

| arm | runs | usable | median | range |
| --- | --- | --- | --- | --- |
| flywheel | 3 | **3** | **30.41%** | 25.78–31.43% |
| hypergraph | 3 | **3** | 21.46% | 12.65–32.43% |
| git (control) | 3 | **0** | — | — |

Per run: flywheel 30.41 / 31.43 / 25.78; hypergraph 12.65 / 32.43 / 21.46.

**Pre-registered verdict: no detectable difference at n=3.** flywheel has the
highest median but its range overlaps hypergraph's. The tooling states this
itself rather than ranking the medians.

**The control arm produced no usable model in any run.** Two of three diverged —
71,290 all-NaN vectors at dim 200 — and the third produced no `vectors.txt` at
all. Both memory-system arms produced 3/3 usable models. Dimension is not the
explanation: flywheel-s2 and flywheel-s3 also used dim 200 and scored 31.43% and
25.78%.

This is the most striking pattern in the data and it must be labelled correctly:
**it is post-hoc.** METRICS.md pre-registered fidelity as an accuracy number, not
as "produced a usable model at all". Treating 0/3 versus 6/6 as a result would be
choosing the hypothesis after seeing the data. It is a strong reason to run a
larger replication with that outcome pre-registered, and nothing more yet.

**Cold-start resilience** — after the classifier fix, no detectable difference:
flywheel 38s / 9 calls, git 81s / 9 calls, hypergraph 43s / 10 calls.

**Throughput** — median tool calls 113 / 81 / 133 (flywheel / git / hypergraph),
median assistant turns 90 / 59 / 87.

**Cost: $2.18 total** for nine two-hour runs, against a $27–49 estimate and a $40
gate. The estimate extrapolated from the pilot's wall-clock, but most of a run is
CPU training with no model calls, so wall-clock is the wrong basis entirely.

**Three analysis defects, each caught before publication, each fatal to the
conclusion:**

1. **Divergence scored as a low number.** All-NaN vectors produced a silent
   0.00%, which reads as "trained badly" rather than "produced nothing usable".
   The evaluator now detects non-finite vectors and reports `TRAINING DIVERGED`;
   diverged runs are excluded from accuracy statistics rather than averaged in
   as zero, which would have dragged the control's mean without explaining it.
2. **The verdict function ranked every measure by highest median**, so on a
   lower-is-better measure it named the **slowest** arm the cold-start leader.
   It is now direction-aware. The same function had also declared a winner off
   two runs on partial data; it now refuses to compare arms with fewer than
   three usable runs.
3. **The productive-action classifier was wrong in two ways that both favoured
   the non-protocol arms.** `cd ~/research && git log` counted as work because
   the prefix match saw `cd`, and every MCP call counted as work including
   `get_node`/`list_nodes` reads. Corrected, the arms orient comparably
   (38/81/43s); before the fix the protocol arm appeared roughly seven times
   slower to start working. That would have been a published headline in exactly
   the wrong direction.

Tests: 117 pass. Checker: 0 violations.

## What this does and does not support

It does not show the protocol helps. It does not show it does not. At three seeds
with overlapping ranges the pre-registered answer is *no detectable difference*,
and that is the honest finding.

Two caveats bound it further. Under pi, arm C ran **without** the skills layer,
which biases against it. And the harness is DeepSeek V4 Pro under pi — "the
protocol helps this agent" would not automatically generalise to Claude Code,
whose path is built and smoke-tested for exactly that replication.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 5fc5885977eee777bd9913a1043a0af5e4799702

## State Impact

- target: protocol-benchmark-4417 — the measured run is complete: 9/9 launched, cut, harvested; 0 boxes leaked; $2.18 total against a $27-49 estimate (wall-clock was the wrong basis — most of a run is CPU training with no model calls). Fidelity, scored by us: flywheel median 30.41% (25.78-31.43, 3/3 usable), hypergraph median 21.46% (12.65-32.43, 3/3 usable), git control 0/3 usable. Pre-registered verdict: NO DETECTABLE DIFFERENCE at n=3 — the leading median's range overlaps. Cold-start also indistinguishable after a classifier fix (38/81/43s). The thrust has its first evidence and it is a null result, which ships as-is.
- target: protocol-benchmark-4417 — post-hoc observation flagged as post-hoc, not a result: the git control produced no usable model in any of three runs (two diverged to 71,290 all-NaN vectors, one produced no vectors), while both memory-system arms produced 3/3. Dimension does not explain it — flywheel also used dim 200 twice and scored 31.43% and 25.78%. METRICS.md pre-registered accuracy, not 'produced a usable model at all', so treating 0/3 vs 6/6 as a finding would be choosing the hypothesis after seeing the data. It is a reason to run a larger replication with that outcome pre-registered.
- target: polished-pond-2718 — the benchmark dataset now exists and is the first real external subject for the visualization work: 9 runs x (fidelity by section, cold-start timings, per-turn token/tool traces) in research/runs/main/analysis.json, with the raw session transcripts harvested alongside.
