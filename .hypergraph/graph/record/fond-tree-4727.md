---
node_id: 0d7bf3cd-5980-5d2f-b7ea-9c8449c3d3b9
slug: fond-tree-4727
title: 'M7: fresh-agent acceptance loop in a3go held end-to-end'
created_at: '2026-08-07T21:15:01+00:00'
parents:
- stormy-dew-2969
summary: ''
flywheel:
  node_id: 88e1294e-6e5a-547b-91fe-8f6892fa6028
  slug: snowy-resonance-9834
  revision: 0
  pushed_at: '2026-08-07T21:22:12+00:00'
  content_sha256: 3d7c629f428bc67a28394f69a66055aec2fcaebee6b6894aa5d77d70956e0705
---
## What

Acceptance test for the adoption path (adoption thrust M7): a fresh agent session was dropped into /Users/theo/a3go with no protocol context beyond the repo's own AGENTS.md, asked to do one genuine unit of work, and the full loop held — orient → work → record → librarian reconcile → mirror push → verify clean.

## Why

The adoption thrust (vast-sky-3964) defined this as the real bar: not that the graphs exist, but that a cold-start agent can land real work through them with zero protocol violations. M5/M6 built the adopted graphs; this tests whether they carry a stranger.

## Method

A general-purpose subagent (no inherited context) was launched in a3go and instructed only to read AGENTS.md, follow the onboarding it prescribes, pick one small genuine unit of work runnable locally (no GPU, ≤15 min compute), and complete it per the repo contract. Its report was then audited against the plan's bar (orient ≤6 calls citing pre-adoption evidence; causally-parented record with valid impacts; no state writes; check exit 0), after which the librarian half ran from this session: hypergraph-reconcile folded the declared impacts into silent-dew-3574 and northern-creek-9091, advanced the HWM to the new record node, regenerated STATE.md, and refreshed the mirror (3 state-node updates pushed byte-identical from plan content, legend already current, `push --verify` against the 121-node archive+mirror union export).

## Result

Loop held end-to-end, zero protocol violations. The agent oriented in 6 tool calls via STATE.md + .hypergraph/AGENTS.md, chose GEO-1's explicit precondition off the adopted frontier (still-recipe-4954's "verify (n,n,1) reproduces 2D Go first"), and produced a real measurement: 16/16 known-answer checks show depth-1 boards are exactly 2D Go (646 topology points, ko/superko/Tromp-Taylor all correct), and on (3,3,1) a corner first move flips Black 100%→1% win (n=128/arm, CI-separated) — cell-type preference is decisive at d=1 yet absent on 4³, giving GEO-1 a measured endpoint. It recorded icy-fjord-0022 causally parented on the design brief with valid impacts, correctly declined to touch state nodes, ran npm test 48/48 + check exit 0, and committed everything (a3go 76db281, e8b801f). Two adoption conventions were exercised live and held: the mirror 403'd on the archive-node parent and the agent correctly parented the mirror copy on the mirror record root (the documented cross-epoch rule), and it resolved the legacy `.gitignore experiments/` convention against the new evidence-committed-by-path contract with a narrow exception rather than skipping evidence. Librarian pass: reconcile folded both impacts, HWM → icy-fjord-0022, mirror verify 0 drift (a3go fec7897). One deliberate deviation, sanctioned by the onboarding docs: the agent verified the mirror via empty re-plan instead of the formal `push --verify` (the export had returned inline, not as a file) — the formal verify ran clean in the librarian pass, and the inline-export ergonomics gap is noted for the CLI backlog.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: c3ef29c19010726fb2b228202b6771ac171ec134

## State Impact

- target: morning-crane-7863 — acceptance test passed: fresh agent completed orient→work→record→reconcile→mirror-verify in a3go with zero protocol violations; adoption thrust delivered end-to-end
- target: bitter-sound-9744 — field dogfooding decided: both target repos adopted (a3go mode A, tbinn mode B) and a cold-start agent landed genuine work through the a3go graphs; four protocol defects found and fixed during dogfooding
