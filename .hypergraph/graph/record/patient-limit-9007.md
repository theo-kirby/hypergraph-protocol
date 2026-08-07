---
node_id: 815ea193-cb04-57da-a8e0-ddbfa5e4e62a
slug: patient-limit-9007
title: 'Decision: forward work as state gaps + decision records; Operator directives enter via the record graph'
created_at: '2026-08-07T10:56:35.933908+00:00'
parents:
- steep-cell-5173
- spring-pine-7256
summary: Forward work = open state-node gaps + immutable decision records; Operator directives enter via the record graph. Frontier opened accordingly.
flywheel:
  node_id: 815ea193-cb04-57da-a8e0-ddbfa5e4e62a
  slug: patient-limit-9007
  revision: 1
  pushed_at: '2026-08-07T18:12:00.956635+00:00'
  content_sha256: 9959b8d30e765e5bf6eb42e2f347f9c1a6c167fccf220344c7ffdfb235fb47e7
---
## What

Settled how forward-looking work is represented (Operator directive, discussed and agreed with the agent): future work lives in the state graph as `Status: open` nodes — claims about gaps — never as task lists; prioritization bets live in the record graph as immutable decision nodes; and Operator directives enter the system as decision record nodes whose `## State Impact` opens the gap, so no state node is ever created without a record pointer.

## Why

Post-viz analysis of this repo's graphs (following the M5 cycle, steep-cell-5173) found the frontier empty while real known ambitions sat outside the graphs — in SPEC's future-work list and in a "Next:" bullet inside a working state node — invisible to hypergraph-orient. Extends the original design decisions (spring-pine-7256): I1 record-first applies to intent exactly as to results.

## Method

Design discussion between Operator and agent. Alternatives considered and rejected: a "Next steps" list state node (task queues rot; nothing forces updates — whereas gap-claims are falsified by work through I2's mandatory impact declaration); per-state-node TODO lists (same rot, scattered); a third "future ideas" graph (duplicates the librarian/checker machinery for the most perishable content; plans decompose fully into gap-claims + decision records); no forward representation at all (arriving agent decides — kept as a principle, but without decision records every agent silently re-litigates settled priorities). Operator's required flow: (1) decision record node capturing intent/constraints/rationale with source attribution; (2) `## State Impact` declaring NEW or delta targets; (3) reconcile folds it onto the frontier with provenance. Granularity rule: architectural capabilities and known gaps earn state nodes; fine-grained tasks belong in neither graph.

## Result

Convention codified in SPEC.md ("Forward work and Operator directives"), hypergraph-record skill (directive decision nodes), and README, commit 038e817. Applied immediately to this repo via this node's impacts: two real gaps open (git-native backend, field dogfooding), the "Next:" bullet moves out of Dogfooding, and SPEC's future-work list shrinks to speculative machinery only. Decision records do not bind later agents — overriding a bet means writing a new decision node.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: 038e8173cef4cb5a1c6c43c9bd621eb89d36a80f

## State Impact

- target: NEW git-native-backend — open: git-native open backend as a drop-in second adapter behind backend/INTERFACE.md; decision on build vs. defer comes after field dogfooding
- target: NEW field-dogfooding — open: apply the protocol to a real external research project; will exercise broken/blocked/superseded statuses, staleness reporting, and multi-agent recording in anger
- target: bold-field-1268 — drop the forward-looking "Next:" bullet; intent now lives on the frontier nodes this decision opens
- target: young-wave-9364 — new claim: SPEC gains the forward-work + Operator-directive conventions
- target: dry-wildflower-2260 — new claim: hypergraph-record covers directive decision nodes (intent before work)