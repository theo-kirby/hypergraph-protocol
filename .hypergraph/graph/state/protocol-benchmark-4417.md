---
node_id: c3e858c6-b1c3-51e2-8487-f66b7a1d67f5
slug: protocol-benchmark-4417
title: Protocol benchmark
created_at: '2026-08-08T17:21:41+00:00'
parents:
- cool-king-8586
summary: ''
---
Status: open

## Current

- **The gap this closes.** Everything to date shows the protocol works *mechanically* — `check` reports 0 violations on three repos, and a fresh agent completed the full loop with zero violations [rec: fond-tree-4727]. No evidence yet shows it makes agent work *better* than plain git. The announcement is the last publication gap, and an announcement with no evidence is a claim, so the Operator parked the release and opened this thrust instead [rec: southern-ridge-1802].
- **The design.** Three isolated agents implement the same paper — word2vec (Mikolov et al. 2013), skip-gram with negative sampling on text8 — on three identical Ascii Box VMs. Arm A has git only, arm B Flywheel, arm C the Hypergraph protocol. Four measures: reproduction fidelity, cold-start resilience, throughput and waste, and a blind judge score. Three seeds per arm, nine runs; one run per arm is an anecdote [rec: southern-ridge-1802].
- **The independent variable is isolated by construction.** box-wheel's primer mixes research discipline with Flywheel mechanics; handing that to one arm and nothing to another would measure *good primer vs no primer*. It is split into `primers/_core.md` (byte-identical for every arm) plus `primers/memory/{git,flywheel,hypergraph}.md`, the only difference, held to within 15% word count by test — measured at 785/761/796 words, a 4.6% spread [rec: twilight-wood-1934].
- **The control is a real control**, taught commit-as-record, a running `NOTES.md`/`DECISIONS.md`/`DEAD-ENDS.md`, branch-per-alternative and log interrogation. If the protocol cannot beat competent git hygiene, that is the finding [rec: twilight-wood-1934].
- **The lab is built and field-proven.** `research/boxlab` adapts box-wheel's control layer (config with credential provenance, ssh-on-stdin box control, arm-aware provisioning, detached runner, experiment driver, spend guard) plus a `lab.py` CLI. Nothing in `research/` ships: both hatchling targets are allow-lists, verified by building the artifacts (wheel 40 files/415 KB, sdist 14 files), and `tests/test_packaging.py` fails if it is ever added [rec: twilight-wood-1934].
- **Cold-start resilience costs nothing to measure, and that is now proven rather than assumed.** Neither harness is passed a resume flag, so killing the session and relaunching leaves only the box's filesystem — exactly the memory system under test. Live on both harnesses, a relaunched session asked what it had just done answered `NO-PRIOR-SESSION` [rec: twilight-wood-1934] [rec: scarlet-orchard-8774].
- **Harness: pi (pi.dev) on OpenRouter, `deepseek/deepseek-v4-pro`, all nine concurrent** — Operator directive. The choice is about risk, not price: a subscription quota wall landing mid-run would truncate arms unevenly while the charts still rendered. A metered API makes that a visible bounded number, gated by a spend guard that can refuse a launch but never kills a running arm [rec: scarlet-orchard-8774].
- **Fidelity is scored by us, never by an arm**, with a pre-registered target fixed before any arm existed: vanilla SGNS on text8, Google analogy total accuracy — 24.16% at dim 100 (arXiv:2009.04413v2). `research/eval/analogy.py` is offline and deterministic, with the 19,544-question set committed beside it so a score cannot drift with a download [rec: twilight-wood-1934].
- **Open and unmitigated:** OpenRouter's `usage` field appeared not to move immediately after a live run, so the spend guard may be partially blind *during* a run and reliable only between runs. Under pi, arm C also runs without the skills layer — `.claude/skills` is a Claude Code convention pi does not read — which is a narrower test that biases against arm C [rec: scarlet-orchard-8774].

## Negative knowledge

- [scope: comparing agent memory systems | confidence: high | evidence: twilight-wood-1934] a primer that bundles research discipline with one system's mechanics cannot be used as an experimental arm — handing it to one arm and nothing to another measures prompt quality, not the system. Arms must share a byte-identical core and differ only in a length-matched section.
- [scope: driving headless agent harnesses | confidence: high | evidence: scarlet-orchard-8774] an agent's run log is not its session record. pi's print mode wrote 82 bytes — the final answer only — for a whole run, while the turn/token/cost tree auto-saved elsewhere on disk; a harvest scoped to the workspace would have destroyed the evidence at teardown and surfaced the loss only at analysis.

## Provenance

- southern-ridge-1802 — Operator directive: publication parked, three-arm benchmark opened; design, arms, measures, seeds
- twilight-wood-1934 — M1: boxlab from box-wheel, the split primer, METRICS.md, packaging answered, first live smoke pass
- scarlet-orchard-8774 — M2: pi/OpenRouter harness, experiment driver, spend guard; cold start proven on both harnesses
