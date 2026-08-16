---
node_id: 50f39fb1-edf8-55f3-a263-213beda9af54
slug: hollow-rain-8997
title: Autonomous operation
created_at: '2026-08-14T13:24:31+00:00'
parents:
- cool-king-8586
summary: 'The tagline claim, held open: the composing loop now exists (hypergraph-dispatch + lanes) and two acceptance dispatches behaved unreconciled; a series of contexts is still unproven — dispatch is the instrument that will test it.'
flywheel:
  node_id: b158e0a7-f464-5c99-93d1-a699d30b8d89
  slug: noisy-lab-4242
  revision: 3
  pushed_at: '2026-08-16T18:35:51+00:00'
  content_sha256: 5ffd41df2fc9e7f38f10302d59f1a174ab31b44bfbcc8bc35c8752988a62447a
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents: []
---
Status: open

## Current

**The claim the project leads with, and the one no state node made until now.** SPEC.md, README.md and AGENTS.md all open with "a substrate for autonomous research and engineering" — the memory layer an agent needs to carry work across months and contexts without a human holding the thread [rec: clever-ledge-6588]. An empty frontier on a known ambition is itself a defect, so this node exists to hold the gap rather than to claim it is closed [rec: late-sage-5549].

- **Proven: a cold-started agent completes one loop unattended.** In a3go a fresh agent given only the repo's AGENTS.md oriented in 6 calls, did genuine frontier work, recorded a causally-parented node with valid impacts, never wrote state, and left the reconcile to the Operator — zero protocol violations [rec: fond-tree-4727]. neural-whoop went further: a whole mode A adoption of 189 legacy nodes, run by an agent that could not ask a question [rec: clever-ledge-6588].
- **Not proven: anything past one loop.** No agent has yet carried work across a *series* of contexts on this substrate, which is the actual claim in the tagline. The protocol benchmark is the only design that would measure it against a control, and it is parked [rec: southern-ridge-1802].
- **"There is no auto-run skill" is falsified at 0.0.11.** `hypergraph-dispatch` is the loop that composes the pieces — orient → claim → work → record → close — aimed at a frontier slug, a prose goal, or a region, under a bounded budget, in a lane of its own (`hypergraph dispatch`, backend/lanes.md) [rec: young-sage-8406] [rec: dry-spark-3491]. The seam went in spec-first: dispatch enters through the record graph as an advisory lane claim, and dispatched agents are contributors by definition [rec: windy-eagle-6074].
- **The pieces an unattended run needs exist and are separately proven**: `orient` reads the frontier read-only, `record` is safe on any branch, fork or machine, `check --since` reaches a contributor who never read AGENTS.md, and `push` stands down at exit 0 rather than failing when publishing is not this checkout's job [rec: placid-ridge-4035]. Dispatch now composes them; what remains unproven is the tagline itself — see below.
- **Two acceptance dispatches ran before any reconcile and behaved** [rec: even-journey-4120] [rec: idle-crow-3832] [rec: ancient-key-8524] [rec: bold-sand-5009]: run 1 claimed a region target, worked one real unit in its lane and closed; run 2, given the same region, read run 1's closed-but-unreconciled lineage, named the avoided target in its `## Why`, and picked elsewhere. That exercises coexisting unreconciled dispatch lineages and claim-reading across the reconcile gap — two of the three surfaces field use had never touched; `superseded` remains unexercised [rec: patient-limit-9007].
- **Not proven, and now testable: a *series* of contexts.** No agent has yet carried work across multiple sessions on this substrate — the actual tagline claim, which only the parked benchmark was ever designed to measure [rec: southern-ridge-1802]. Dispatch is the instrument that will test it without that harness: repeated dispatches over a reconcile cadence are exactly "resume the frontier and keep going" [rec: young-sage-8406]. This node stays open until that evidence exists.

## Negative knowledge

None yet.

## Provenance

- clever-ledge-6588 — the tagline this node holds open, published in README, SPEC and AGENTS.md
- late-sage-5549 — the decision that an empty frontier on a known ambition is a defect
- fond-tree-4727 — the a3go acceptance loop: one full unattended cycle, zero violations
- clever-ledge-6588 — neural-whoop adopted by an agent that could not ask a question
- southern-ridge-1802 — the benchmark, the only design that would measure past one loop, parked
- calm-sand-3399 — the five skills, all session-initiated
- placid-ridge-4035 — orient/record/check --since/push stand-down, the pieces an unattended run needs
- patient-limit-9007 — the three protocol surfaces field use has still not exercised
- windy-eagle-6074 — the lanes seam and SPEC's Dispatch and lanes, spec-first
- young-sage-8406 — the sixth skill: the loop that composes the pieces
- dry-spark-3491 — the local lane provider CLI
- even-journey-4120 — acceptance run 1's lane claim at the state-root region
- idle-crow-3832 — run 1's unit: one aimed loop, in a lane, zero violations
- ancient-key-8524 — run 2's claim, naming and avoiding run 1's
- bold-sand-5009 — run 2's unit: claim-avoidance across the reconcile gap proven
- vast-birch-5192 — Operator directive: the release label is 0.0.11, not 0.9.0
