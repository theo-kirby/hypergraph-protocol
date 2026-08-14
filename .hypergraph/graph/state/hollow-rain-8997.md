---
node_id: 50f39fb1-edf8-55f3-a263-213beda9af54
slug: hollow-rain-8997
title: Autonomous operation
created_at: '2026-08-14T13:24:31+00:00'
parents:
- cool-king-8586
summary: 'The tagline claim, held open: one unattended loop is proven in the field, nothing past one loop is, and there is no auto-run skill. The pieces exist; the loop composing them does not.'
flywheel:
  node_id: b158e0a7-f464-5c99-93d1-a699d30b8d89
  slug: noisy-lab-4242
  revision: 1
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: 84eab77063bd1b501a5bddaddabd31e1a03719562e9ca8a7d051dd4ac685cb67
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents: []
---
Status: open

## Current

**The claim the project leads with, and the one no state node made until now.** SPEC.md, README.md and AGENTS.md all open with "a substrate for autonomous research and engineering" — the memory layer an agent needs to carry work across months and contexts without a human holding the thread [rec: clever-ledge-6588]. An empty frontier on a known ambition is itself a defect, so this node exists to hold the gap rather than to claim it is closed [rec: late-sage-5549].

- **Proven: a cold-started agent completes one loop unattended.** In a3go a fresh agent given only the repo's AGENTS.md oriented in 6 calls, did genuine frontier work, recorded a causally-parented node with valid impacts, never wrote state, and left the reconcile to the Operator — zero protocol violations [rec: fond-tree-4727]. neural-whoop went further: a whole mode A adoption of 189 legacy nodes, run by an agent that could not ask a question [rec: clever-ledge-6588].
- **Not proven: anything past one loop.** No agent has yet carried work across a *series* of contexts on this substrate, which is the actual claim in the tagline. The protocol benchmark is the only design that would measure it against a control, and it is parked [rec: southern-ridge-1802].
- **There is no auto-run skill.** All five skills are session-initiated; nothing packages "resume the frontier and keep going" [rec: calm-sand-3399].
- **The pieces an unattended run needs exist and are separately proven**: `orient` reads the frontier read-only, `record` is safe on any branch, fork or machine, `check --since` reaches a contributor who never read AGENTS.md, and `push` stands down at exit 0 rather than failing when publishing is not this checkout's job [rec: placid-ridge-4035]. What is missing is the loop that composes them.
- Field use has still not exercised `superseded`, staleness reporting across long reconcile gaps, or parallel-agent recording — the three things a long unattended run would hit first [rec: patient-limit-9007].

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
