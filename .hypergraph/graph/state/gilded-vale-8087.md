---
node_id: c89d40e9-ccbc-58ee-a04e-ec69a55b6c33
slug: gilded-vale-8087
title: Collaboration
created_at: '2026-08-09T12:05:09+00:00'
parents:
- cool-king-8586
summary: 'Parallel and multi-contributor work: contributors record, the maintainer reconciles. v0.0.5 shipped all three Operator bets — ancestry frontier, publish guards, CI enforcement — verified on this repo own two-tip record DAG. Open: no multi-machine run yet.'
flywheel:
  node_id: c70be6f8-ea12-5dd8-9a36-230e248fbb2a
  slug: restless-butterfly-5749
  revision: 1
  pushed_at: '2026-08-09T12:28:31+00:00'
  content_sha256: 94c3ea79a6be7489d3b2f5b0724565436425f682d86171a060bea851b5c4520e
---
Status: working

## Current

- **The settled framing: the record/state split already *is* the fork/merge split**, and it was not designed for that. The record graph is append-only with one file per node, so two branches produce two new files and merge with zero conflicts, always. The state graph is single-writer by I3, so concurrent branches edit the same files. The collaboration rule therefore falls out of the invariants rather than out of new machinery: **contributors record; the maintainer reconciles.** A PR carries facts; main carries claims [rec: vast-rain-4873]. SPEC v0.0.5 states it as a Collaboration convention [rec: placid-ridge-4035].
- **All three Operator bets are shipped** [rec: placid-ridge-4035]:
  - **Reconcile is maintainer-on-main only** — stated in SPEC, in the reconcile skill's When-To-Use, and in AGENTS.md; the record skill says the converse, that recording is safe on any branch, fork or machine [rec: placid-ridge-4035].
  - **CI enforcement fails the PR** — `hypergraph check --since <ref>` reports a branch that changed files and added no record node as an I1 violation. Three-dot range, so it is what the branch *adds*; graph, STATE.md and cache paths are excluded so a reconcile-only branch is not asked to record itself [rec: placid-ridge-4035].
  - **The mirror publishes from CI on main only** — `push` gates on `publish_branch:` (else `origin/HEAD`, else `main`) and stands down at exit 0 when the credentials do not own the mirror. Two workflow templates ship; the PR check is installed in this repo, the publish job is not [rec: placid-ridge-4035].
- **I5 is now an ancestry frontier.** `high_water_mark:` takes one or more record tips, and reconciled means *ancestor of some tip*. This is the fix for the defect that mattered: the old timestamp comparison did not fail, it **forgot** [rec: placid-ridge-4035].
- **Verified on this repo's own two-tip DAG.** The hg-viz merge had already left nine nodes on `wise-river-3571` that are not ancestors of the mark; they were folded correctly at the time only because the reconcile ordering happened to be favourable. Under the new rule all nine surface, the migration hint fires, and `hwm --suggest` prints the exact frontier, adopted in this pass [rec: placid-ridge-4035].
- **What git already provides, verified rather than assumed** [rec: vast-rain-4873]: record-node merges never conflict; a slug collision across branches surfaces as a loud git add/add conflict, which matters because `node_id = uuid5(slug)` makes a silent collision an identity collision; the merged record DAG shows the fork truthfully; `--repo-auto` already stamps branch and commit into every node; and a record node arrives in the PR diff as a file, so the claim gets code review beside the code that justifies it.
- Both naming hazards are settled: SPEC distinguishes a repo fork (same graph, same slugs, same ids — a PR merges back into it) from `import --fork` (a new project from someone else's graph), and the reconcile skill's guardrails say to start from `sync` after a merge, never a bare `check` [rec: placid-ridge-4035].
- **Still open, and narrower than the gap that opened this node** [rec: placid-ridge-4035]: no multi-machine workflow has yet been *run* end to end — the model is proven by construction and by tests, not by two humans and a fork; `.gitattributes` for STATE.md was scoped and not built, since regeneration already resolves it and a merge driver would be a second mechanism for the same problem; and the publish workflow is shipped but unexercised, because this project still publishes from the maintainer's machine.

## Negative knowledge

- [scope: enumerating unreconciled work after a git merge | confidence: high | evidence: vast-rain-4873, placid-ridge-4035] a high-water mark compared by timestamp silently drops every record node that was authored before the last reconcile but merged after it — the checker reports 0 unreconciled and 0 violations while the work is gone from the frontier permanently. Reachability in the causal DAG is the only sound test; wall-clock ordering is not, and a fleet of machines with skewed clocks widens the window.
- [scope: changing the rule a stored marker is interpreted by | confidence: high | evidence: placid-ridge-4035] the algorithm was the easy half; the migration was the design problem. Switching from timestamps to ancestry makes an existing graph surface side branches that *were* folded, which reads as "your work vanished" and invites folding them a second time. A rule change over persisted state needs the old rule's intent expressible in the new one — here `hwm --suggest` — and needs the surfaced items distinguished from genuinely new ones, as info rather than as a failure.
- [scope: validating markdown that git may have merged | confidence: high | evidence: vast-rain-4873] a node body carrying a literal git conflict-marker block passes `check` at 0 violations, commits, and is then published to the append-only public mirror. A validator for files that a merge tool can write must reject conflict markers explicitly; no other invariant catches them.
- [scope: publishing to an append-only store from a branch | confidence: high | evidence: vast-rain-4873] nothing in the push path reads HEAD, so work can be published from a feature branch that is never merged, leaving nodes on a public graph with no local counterpart and no way to retract them cleanly. Anything that writes to an append-only external store needs a branch guard.
- [scope: guarding a step that runs before its own commit | confidence: high | evidence: placid-ridge-4035] the dirty-tree guard that seemed to belong beside the branch guard was wrong and was dropped. Reconcile publishes *before* it commits, deliberately, so `push`'s frontmatter writes land in the same `git add` — which makes a dirty graph the expected state at push time. A guard has to be derived from the workflow it protects, not from the general shape of the risk.

## Provenance

- vast-rain-4873 — the investigation that opened this gap: three reproduced defects and three Operator bets
- placid-ridge-4035 — v0.0.5 closes it: ancestry frontier, conflict markers, publish guards, doctrine and CI
