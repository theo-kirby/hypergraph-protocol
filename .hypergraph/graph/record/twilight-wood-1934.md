---
node_id: e9bafb4d-0fbc-5d3f-862b-a723370780fa
slug: twilight-wood-1934
title: 'M1: boxlab built from box-wheel; split primer; cold start proven live'
created_at: '2026-08-08T16:56:10+00:00'
parents:
- southern-ridge-1802
summary: ''
flywheel:
  node_id: ace40965-316c-5898-a9d6-c9730f645414
  slug: red-sun-7698
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 882bfdb67ee6cbd1fb8659d1137984c35fd6c92c30b592b956aefc03af834a1d
  parents_sha256: 3a2f6aaddf88e3f9d0a45704cdf04b946be418c8f31fc2349b43d1282d83c28f
  parents:
  - 60dad4c5-2fbe-569b-acec-07595b948638
---
## What

Built `research/boxlab` — the lab that runs the three-arm benchmark — and proved
the whole chain live on one box. Also landed the split primer (the experiment's
independent variable) and `research/METRICS.md` (the pre-registered measurement
spec).

Nothing in `research/` ships. Both hatchling targets are allow-lists, verified
empirically by building both artifacts: the wheel is 40 files / 415 KB
(`hypergraph_protocol.py` + skills + templates + dist-info) and the sdist 14
files. `tests/test_packaging.py` fails if `research/` is ever added to either
list, which answers the Operator's question — the repo already separates the
package from the workshop.

## Why

Follows from `southern-ridge-1802`, which opened this thrust and named M1 as
"build the Box integration". The Operator then pointed at **box-wheel**
(`~/box-wheel`), a predecessor project of theirs that already unifies Box + Flywheel
into a control centre for autonomous agents. Reading it changed M1 from "build an
agent platform" to "adapt one that works", and corrected the launch mechanism:
`box prompt` gives a headless provider-run agent, but the Operator wants the box
**ssh-provisioned** with Claude authenticated on the subscription — which is
exactly what box-wheel already does.

Three Operator decisions set the shape: the code lives in `research/` here (not
in box-wheel) so the work lands in this project's graph; arm A is a *real*
control taught git-as-memory rather than an unprompted baseline; and each arm is
one flat mission, not a box-wheel campaign — the middle-out methodology is itself
a memory-and-structure system and would contaminate the comparison.

## Method

**Adapted from box-wheel**, Claude-only and trimmed (codex, pi, Kaggle, the TUI,
the campaign daemon all dropped): `config.py` (credential resolution with
per-variable provenance), `box_ctl.py` (lifecycle + `box ssh <id> bash -s` with
the script on **stdin**), `provision.py` (arm-aware idempotent bash),
`runner.py` (detached `claude -p`), `arms.py`, and a `lab.py` CLI. Its
load-bearing lessons carried over verbatim: secrets on stdin never argv;
`CLAUDE_CODE_OAUTH_TOKEN` and never `ANTHROPIC_API_KEY`; a launch-ssh timeout
*is* the successful detached launch; the READY-but-not-ssh-able boot gap;
`< /dev/null` to release the ssh channel.

**The independent variable.** box-wheel's primer is 283 lines mixing generic
research discipline with Flywheel mechanics. Handing that to one arm and nothing
to another would measure *good primer vs no primer*. So it is split:
`primers/_core.md` (identical for every arm — discipline, publishing, definition
of done) plus `primers/memory/{git,flywheel,hypergraph}.md`, which is the **only**
difference between arms. A test holds the three within 15% word count; they came
out at 785 / 761 / 796 words, a 4.6% spread.

**Pre-registered metrics** (`research/METRICS.md`), fixed before any arm runs.
The fidelity target is the literature band for vanilla SGNS on text8, Google
analogy total accuracy, from arXiv:2009.04413v2 Tables IX/XII/XIII: 18.60% at
dim 50, **24.16%** at dim 100 (semantic 20.50 / syntactic 26.77), 27.13% at
dim 200 — all at window 10, k=1, 20 epochs. Scoring: `reproduced` at ≥20% and
`matched-literature` at ≥24.16%, both at dim ≥100, with the raw number reported
regardless. Fidelity is scored **by us** on the arm's `vectors.txt`; an arm never
grades itself.

**Live smoke test**, arm C (the heaviest provisioning path), box `bx_rwjwxxs3`:
create → ssh-gate → provision → launch → run → kill → relaunch → stop.

## Result

**SMOKE PASS.** Every link in the chain works, and the experiment's riskiest
assumption is now retired empirically rather than assumed.

| Step | Outcome |
| --- | --- |
| provision (uv + `uv tool install hypergraph-protocol` + `skills install`) | ok — "Installed 1 executable: hypergraph" |
| launch detached under the subscription OAuth token | ran, finished in ~17s |
| mission artifact written | yes (`SMOKE-OK …`) |
| kill + relaunch | **`NO-PRIOR-SESSION`** |
| teardown | box stopped, `box list` reports 0 running |

The last row is the important one. `claude -p` keeps no conversation history
without `--resume`/`--continue`, and `runner.py` never passes them, so kill +
relaunch is a **genuine cold start** — the only continuity is the box's
filesystem, which is precisely the memory system under test. Asked what it had
written moments earlier, from memory alone, the relaunched session answered
`NO-PRIOR-SESSION`. Cold-start resilience is therefore measurable for free, with
no extra mechanism, and `tests/test_boxlab.py::test_relaunch_is_a_genuine_cold_start`
guards the property against a future flag change.

The published 0.0.2 CLI installs and runs on a fresh box via `uv tool install`
plus `hypergraph skills install --user` — the real adopter route, incidentally
re-verified.

The stream-json `result` event carries everything measure 3 needs, confirmed on
the captured log: `num_turns`, `duration_ms`, `total_cost_usd`, and full token
usage including cache reads. The trivial 2-turn smoke mission reported
`total_cost_usd` 0.0994.

Tests: 90 pass (72 before, 18 new). Checker: 0 violations.

**Open risk this surfaced.** That $0.099 for two turns is a notional
subscription-equivalent figure, but it scales: nine boxes running for hours will
consume real subscription quota, and box-wheel records that the Anthropic OAuth
usage endpoint 429s hard under polling. A quota wall mid-run would truncate arms
unevenly and silently bias the comparison. Not yet mitigated.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 0e40070428e5470b895824effbf50d6c99401c95

## State Impact

- target: NEW protocol-benchmark — M1 delivered: research/boxlab adapted from box-wheel (config/box_ctl/provision/runner/arms + lab.py CLI), the split primer (_core.md identical per arm + three length-matched memory sections, 4.6% spread) and METRICS.md pre-registered with the text8/Google-analogy literature band (24.16% at dim 100, arXiv:2009.04413v2). Smoke test PASSED live on box bx_rwjwxxs3: provision, detached subscription-authenticated launch, mission ran, box freed. Cold-start resilience is measurable with no extra mechanism — kill + relaunch is a genuine cold start because claude -p keeps no history without --resume/--continue, confirmed by NO-PRIOR-SESSION on a real box. Publication remains parked. Next: M2 harness, then the measured run.
- target: weathered-union-7494 — packaging question answered empirically: the distribution is an allow-list, not the repo. Built artifacts measure 40 files/415 KB (wheel: hypergraph_protocol.py + skills + templates) and 14 files (sdist). research/ ships nothing, and tests/test_packaging.py now fails if it is ever added to either hatchling include list. Incidentally re-verified: the published 0.0.2 installs on a fresh box via uv tool install + hypergraph skills install --user.
- target: bitter-sound-9744 — a third dogfooding surface opened: agents on fresh cloud boxes adopting the protocol from PyPI with no prior context, as one arm of a controlled comparison against git and Flywheel. Unlike a3go and tbinn this one has a control group, so it can measure whether the protocol helps rather than only whether it holds.
