---
node_id: c89d40e9-ccbc-58ee-a04e-ec69a55b6c33
slug: gilded-vale-8087
title: Collaboration
created_at: '2026-08-09T12:05:09+00:00'
parents:
- cool-king-8586
summary: Contributors record, the maintainer reconciles — a rule that falls out of the invariants. All three Operator bets shipped and CI is live; open on any run by two humans and a fork.
flywheel:
  node_id: c70be6f8-ea12-5dd8-9a36-230e248fbb2a
  slug: restless-butterfly-5749
  revision: 3
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: 42e75ac046795c408fcd8d5531f0445b8acc9f628ffe375837d89aead18f6d00
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

- **The settled framing: the record/state split already *is* the fork/merge split**, and it was not designed for that. The record graph is append-only with one file per node, so two branches produce two new files and merge with zero conflicts, always; the state graph is single-writer by I3, so concurrent branches edit the same files. The rule therefore falls out of the invariants rather than out of new machinery: **contributors record; the maintainer reconciles.** A PR carries facts; main carries claims [rec: vast-rain-4873]. SPEC v0.0.5 states it as a convention [rec: placid-ridge-4035].
- **All three Operator bets shipped** [rec: placid-ridge-4035]: reconcile is maintainer-on-main only, stated in SPEC, in the reconcile skill and in AGENTS.md, with the record skill saying the converse; **CI enforcement fails the PR**, since `check --since <ref>` reports a branch that changed files and added no record node as an I1 violation, over a three-dot range so it is what the branch *adds*, with graph and STATE.md paths excluded so a reconcile-only branch is not asked to record itself; and **the mirror publishes from CI on main only**.
- **I5 is now an ancestry frontier**: `high_water_mark:` takes one or more record tips and reconciled means *ancestor of some tip*. This is the fix for the defect that mattered — the old timestamp comparison did not fail, it **forgot** [rec: placid-ridge-4035]. Verified on this repo's own two-tip DAG, where a merge had already left nine nodes that are not ancestors of the mark; under the new rule all nine surface, the migration hint fires, and `hwm --suggest` prints the exact frontier [rec: placid-ridge-4035].
- **What git already provides, verified rather than assumed** [rec: vast-rain-4873]: record-node merges never conflict; a slug collision across branches surfaces as a loud git add/add conflict, which matters because `node_id = uuid5(slug)` makes a silent collision an identity collision; the merged record DAG shows the fork truthfully; `--repo-auto` stamps branch and commit into every node; and a record node arrives in the PR diff as a file, so the claim gets code review beside the code that justifies it.
- **The CI half is live, not just designed** [rec: long-peak-1620]. Both workflows are installed here and were green on their first run, which makes the mirror a build artifact of the default branch written by CI rather than by a laptop.
- **Still open, and narrower than the gap that opened this node** [rec: placid-ridge-4035] [rec: long-peak-1620]: no multi-machine workflow has been *run* end to end — the model is proven by construction, by tests and by this repo's own CI, but not by two humans and a fork; `check --since` has never rejected a real outside contribution, only a synthetic one; and `.gitattributes` for STATE.md was scoped and not built, since regeneration already resolves it and the CI freshness gate catches a stale one.

## Negative knowledge

- [scope: enumerating unreconciled work after a git merge | confidence: high | evidence: vast-rain-4873, placid-ridge-4035] a high-water mark compared by timestamp silently drops every record node that was authored before the last reconcile but merged after it — the checker reports 0 unreconciled and 0 violations while the work is gone from the frontier permanently. Reachability in the causal DAG is the only sound test; wall-clock ordering is not, and a fleet of machines with skewed clocks widens the window.
- [scope: changing the rule a stored marker is interpreted by | confidence: high | evidence: placid-ridge-4035] the algorithm was the easy half; the migration was the design problem. Switching from timestamps to ancestry makes an existing graph surface side branches that *were* folded, which reads as "your work vanished" and invites folding them a second time. A rule change over persisted state needs the old rule's intent expressible in the new one — here `hwm --suggest` — and needs the surfaced items distinguished from genuinely new ones, as info rather than as a failure.
- [scope: validating markdown that git may have merged | confidence: high | evidence: vast-rain-4873] a node body carrying a literal git conflict-marker block passes `check` at 0 violations, commits, and is then published to the append-only public mirror. A validator for files that a merge tool can write must reject conflict markers explicitly; no other invariant catches them.
- [scope: publishing to an append-only store from a branch | confidence: high | evidence: vast-rain-4873] nothing in the push path reads HEAD, so work can be published from a feature branch that is never merged, leaving nodes on a public graph with no local counterpart and no way to retract them cleanly. Anything that writes to an append-only external store needs a branch guard.
- [scope: guarding a step that runs before its own commit | confidence: high | evidence: placid-ridge-4035] the dirty-tree guard that seemed to belong beside the branch guard was wrong and was dropped. Reconcile publishes *before* it commits, deliberately, so `push`'s frontmatter writes land in the same `git add` — which makes a dirty graph the expected state at push time. A guard has to be derived from the workflow it protects, not from the general shape of the risk.

## Provenance

- vast-rain-4873 — the investigation that opened this gap: three reproduced defects and three Operator bets
- placid-ridge-4035 — v0.0.5 closes it: ancestry frontier, conflict markers, publish guards, doctrine and CI
- long-peak-1620 — both workflows installed and green; the publish job reaches the mirror over REST
