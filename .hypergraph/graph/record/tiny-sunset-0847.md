---
node_id: a3da8fba-2b59-5641-961b-144fff063777
slug: tiny-sunset-0847
title: 'Blind-agent test: machinery discovered, obligation missed — AGENTS.md onboarding added'
created_at: '2026-08-07T13:05:25.770156+00:00'
parents:
- morning-rain-7488
summary: Blind-test agent used the graphs as app data, recorded nothing; AGENTS.md onboarding + checker blind-spot finding.
flywheel:
  node_id: a3da8fba-2b59-5641-961b-144fff063777
  slug: tiny-sunset-0847
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 74ba4c661f5cb7155d04331991d9234e822677a905dac553572aa80464b47a15
  parents_sha256: 8e27e131262985ce30b35a404b3ed0817727367435268884d5a891a9ccdd3f89
  parents:
  - 27fef7d4-de86-570b-9722-68d715b0eac1
---
## What

Analyzed how a protocol-naive agent behaved when handed a feature task in this repo with zero mention of Hypergraph, and shipped the fix: AGENTS.md (agent onboarding, record discipline stated as non-negotiable) with CLAUDE.md containing only `@AGENTS.md`.

## Why

Deliberate Operator-run experiment following the fourth-view feature work (morning-rain-7488): the protocol's weakest link was hypothesized to be discoverability without invocation. Pre-registered prediction: the agent ships the feature but skips record/reconcile.

## Method

Audit of the blind agent's session artifacts: git status/diff, cache mtimes vs. session timeline, live record-graph export vs. cache, checker run, test run.

## Result

Findings: (1) the agent found and used the machinery — refreshed .hypergraph/cache/ from live Flywheel exports, ran render (STATE.md byte-identical) and viz — but treated the graphs as app data for its feature, not as the project's memory: zero record nodes, zero git commits. Discovery is not the bottleneck; legibility of the obligation is. (2) It correctly never touched state nodes or hand-edited STATE.md (I3 held vacuously). (3) The pre-registered prediction erred in one place: it assumed the checker would flag the omission, but the checker only detects unreconciled impacts — unrecorded work is invisible to it by construction; the repo HEAD sitting ahead of the newest record node's head_commit_sha is the detectable proxy (added to SPEC future work as a repo-drift check). Fixes shipped in commit 57c7c0f: AGENTS.md + CLAUDE.md pointer, README viz-doc drift corrected, SPEC future-work entry.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: 57c7c0f9b1bbca9f3f0a80f089c6c1894b0aec58

## State Impact

- target: bold-field-1268 — new claim: blind-agent test result — machinery discovered and used, record obligation missed; AGENTS.md onboarding is the countermeasure
- target: wandering-sun-8831 — new negative knowledge: the checker cannot detect unrecorded work (only unreconciled impacts); repo-drift proxy needed
- target: dry-wildflower-2260 — new claim: AGENTS.md (CLAUDE.md → @AGENTS.md) makes the record discipline legible to arriving agents outside the skills channel