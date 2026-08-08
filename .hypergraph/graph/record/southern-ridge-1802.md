---
node_id: 9cbc891d-0d97-591a-8e1e-5cdd0382ea5a
slug: southern-ridge-1802
title: 'Decision: publication parked; three-arm protocol benchmark opened'
created_at: '2026-08-08T16:29:33+00:00'
parents:
- northern-willow-0469
- lawful-birch-4414
summary: ''
---
## What

Operator directive (2026-08-08), recorded before any work exists (SPEC: Forward work).
Three decisions:

1. **Publication is parked.** The 0.1.0 release and the spec-first announcement are
   Operator-gated, not agent work. Both stay pending, with no date. No agent work
   proceeds on either until the Operator says so.
2. **A new thrust opens: measure the protocol.** A three-arm controlled experiment on
   Ascii Box VMs. Three isolated agents implement the same paper — arm A with git
   only, arm B with Flywheel, arm C with the Hypergraph protocol — and the run data
   comes back for analysis.
3. **Secondary: visualization improvements.** Scope not yet set; the benchmark data is
   the intended first real dataset to render.

## Why

The project has never measured its own claim. Everything to date is construction and
dogfooding. The protocol works *mechanically* — `check` reports 0 violations on three
repos, and a fresh agent completed the full loop with zero violations
[rec: fond-tree-4727]. No evidence exists that it makes agent work *better* than plain
git.

That matters most for the one gap left in publication: the announcement. An
announcement with no evidence is a claim. The Operator chose to build the evidence
first and hold the release.

Cold-start resilience is the specific claim under test. Hypergraph exists so a fresh
agent lands productive on an unfamiliar project. `fond-tree-4727` showed one fresh
agent doing that once, inside a project already under the protocol, with no control
arm. That is an existence proof, not a comparison.

## Method

Design as directed by the Operator, plus the environment constraints found during
recon on 2026-08-08.

**Environment.** Ascii Box (`box.ascii.dev`). The CLI is installed at
`~/.ascii/bin/box`; it was *not* signed in at record time (`box limits` returns HTTP
401, `unauthorized`). Primitives confirmed from `box --help`:
`new`, `fork`, `stop`, `resume`, `extend`, `ssh`, `scp`, `snapshot`, `interrupt`,
`events`, `prompt`. Two of these decide the harness design:

- `box prompt --provider claude-code <id> "<prompt>"` runs the agent **inside** the
  box. Providers are `codex` and `claude-code`.
- `box events <id> --follow --json` streams state changes *and* agent chat events as
  JSONL. That is the data-capture channel — no in-box instrumentation needed.

Non-interactive auth is `BOX_API_KEY` plus `box login "$BOX_API_KEY" --json`; every
command takes `--json`. Hardware is 4 vCPU / 8 GB with **no GPU**. Price is
$20 = 555 hours.

**Isolation by fork, not by rebuild.** One base box (toolchain, paper, fresh git repo,
hidden eval script) is forked three times from its snapshot. The arms then differ only
by the prompt prefix, which removes the largest confound at no cost.

**Arms**, sharing one identical prompt body:

- **A (control)** — git only. No Flywheel, no Hypergraph.
- **B** — plus Flywheel, with usage tips, on a Flywheel graph.
- **C** — plus the Hypergraph protocol.

**Paper: word2vec** (Mikolov et al., 2013), skip-gram with negative sampling on the
text8 corpus. Chosen for a checkable headline number (word-analogy accuracy), CPU
feasibility inside 4 vCPU / 8 GB, and a few hours of honest work with real pitfalls
(subsampling, the 0.75 negative-sampling exponent, learning-rate decay). Rejected:
Raft — large surface and strong memory pressure, but no single checkable headline
number; HyperLogLog — crisp but small enough that a strong agent finishes in about an
hour, which cannot separate the arms.

**Measures.** All four, selected by the Operator. The eval script is written and frozen
*before* the run and is hidden from the arms:

1. **Reproduction fidelity** — analogy accuracy against a target fixed in advance.
2. **Cold-start resilience** — kill the agent mid-run, start a fresh one on the same
   box, measure time-to-productive. This is the arm-differentiating test.
3. **Throughput and waste** — work units per hour, tokens, and time lost in repeated
   dead ends, extracted from the event stream and the git log.
4. **Blind judge score** — a separate model reads the final repo against a fixed
   rubric, with the arm identity withheld.

**Seeds.** One run per arm is an anecdote; agent-run variance is large. The harness
defaults to repeated seeds — 3 per arm, 9 boxes — which the price makes trivial.

**Scope guard.** The Box integration is dev-only and env-gated. It is research tooling
for this repo and must never become a dependency of the shipped
`hypergraph-protocol` package.

## Result

No code yet — this node is the decision. Planned milestones:

- **M1** — Box integration: env-gated, dev-only wrapper over the CLI.
- **M2** — Harness: base box, fork x3, the three prompt bundles, event capture per arm.
- **M3** — Measurement: frozen eval script, kill/resume protocol, waste extraction,
  judge rubric.
- **M4** — Harness smoke test on a throwaway box.
- **M5** — The measured run: 3 arms x 3 seeds, a few hours each.
- **M6** — Analysis and charts. This feeds the visualization work.

**Open risks.**

- `box prompt` agent-run semantics are unverified: turn boundaries, how a run ends, and
  whether `interrupt` plus a new `prompt` gives a *genuine* cold start rather than a
  session that keeps its context. M1 must prove this on one box before M2 is built. If
  it does not give a real cold start, measure 2 needs another mechanism.
- The fidelity target for word2vec analogy accuracy on text8 is not yet fixed. It must
  be set from the literature before any arm starts, or fidelity is unfalsifiable after
  the fact.
- The arm B and arm C prompt prefixes are themselves a confound. If they differ in
  length or quality, the experiment measures prompt-writing, not protocols. They must
  be matched, and the matching rule must be stated before the run.

**Blocked on the Operator** for two inputs: `box onboard` sign-in, and a `BOX_API_KEY`
in `.env` from `box api-key create`.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 8cea832ea00bb979ac0f3610de15a3bdc377f3db

## State Impact

- target: weathered-union-7494 — publication parked by Operator directive: the 0.1.0 release and the spec-first announcement are both pending Operator decisions with no date, and no agent work proceeds on either. Recorded for when it resumes: the v0.1 gate (git-native backend) is met, and four changes are shipped but unreleased — MIT/PEP 639 metadata (absent from the published 0.0.2), fork-import, the verify mirror_roots exemption, and the mode-B epoch marker fix.
- target: NEW protocol-benchmark — new thrust: measure the protocol against controls, because no evidence yet distinguishes it from plain git. Three-arm experiment on Ascii Box VMs (A git-only, B +Flywheel, C +Hypergraph), forked from one base box, implementing word2vec (Mikolov 2013) on text8, over four measures: reproduction fidelity, cold-start resilience, throughput/waste, blind judge score; 3 seeds per arm. Open, and blocked on the Operator for box sign-in plus BOX_API_KEY. Box integration stays dev-only and env-gated — never a dependency of the shipped package.
- target: polished-pond-2718 — visualization improvements requested by the Operator; scope not yet set. The benchmark run data from M6 is the intended first real dataset to render.
