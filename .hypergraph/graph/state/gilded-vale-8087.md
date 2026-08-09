---
node_id: c89d40e9-ccbc-58ee-a04e-ec69a55b6c33
slug: gilded-vale-8087
title: Collaboration
created_at: '2026-08-09T12:05:09+00:00'
parents:
- cool-king-8586
summary: 'Open gap: parallel and multi-contributor work — worktrees, branches, forks, PRs, cloud fleets. The record/state split is already the fork/merge split, so contributors record and the maintainer reconciles. Three defects reproduced, three Operator bets taken, nothing implemented yet.'
flywheel:
  node_id: c70be6f8-ea12-5dd8-9a36-230e248fbb2a
  slug: restless-butterfly-5749
  revision: 0
  pushed_at: '2026-08-09T12:06:39+00:00'
  content_sha256: a30afa46f958c077b1f819051b67b5273e3a2b3e617e5da9b44f647b745f8082
---
Status: open

## Current

**The gap this closes.** Every workflow proven so far is one writer on one machine. The next projects are not: the Operator on a laptop, several cloud agents in parallel, and outside contributors who fork a public repo and open a PR with no access to it. Nothing in the protocol, the tool or the skills addresses concurrency, and three defects that silently lose work were reproduced [rec: vast-rain-4873].

- **The settled framing: the record/state split already *is* the fork/merge split**, and it was not designed for that. The record graph is append-only with one file per node, so two branches produce two new files and merge with zero conflicts, always. The state graph is single-writer by I3, so concurrent branches edit the same files. The collaboration rule therefore falls out of the invariants rather than out of new machinery: **contributors record; the maintainer reconciles.** A PR carries facts; main carries claims [rec: vast-rain-4873].
- **Three Operator bets, taken before any implementation** [rec: vast-rain-4873]:
  - **Reconcile is maintainer-on-main only.** Contributors and cloud agents record only. One pass folds every merged branch at once, which is better than N sequential passes because the librarian sees the whole batch and writes one coherent claim. [rec: vast-rain-4873]
  - **CI enforcement fails the PR.** `check --since <ref>` reporting "code changed, no record node" as a red check is the only mechanism that reaches a contributor who never reads AGENTS.md. Opt-in per repo. [rec: vast-rain-4873]
  - **The mirror publishes from CI on main only** — a build artifact of the default branch, like a docs site. Credentials live in one repo secret, so contributors and cloud agents never hold them, which preserves the mirror invisibility won in calm-sand-3399. [rec: vast-rain-4873]
- **What git already provides, verified rather than assumed** [rec: vast-rain-4873]: record-node merges never conflict; a slug collision across branches surfaces as a loud git add/add conflict, which matters because `node_id = uuid5(slug)` makes a silent collision an identity collision; the merged record DAG shows the fork truthfully; `--repo-auto` already stamps branch and commit into every node; and a record node arrives in the PR diff as a file, so the claim gets code review beside the code that justifies it.
- **Open work, none of it started.** Ancestry-based high-water mark; conflict-marker detection in `check`; a publish-branch and dirty-tree guard on `push`; `push` no-op instead of exit 2 when a mirror is configured but the credentials are not the owner's; the maintainer-reconciles rule written into SPEC; a publish-branch gate in the reconcile skill; `.gitattributes` plus a documented post-merge regeneration step for STATE.md; `check --since <ref>`; and two GitHub Action templates [rec: vast-rain-4873].
- **Two naming hazards to settle in the same pass** [rec: vast-rain-4873]: "fork" means two unrelated things (a GitHub repo fork keeps the same graph, the same slugs and the same node ids, while `import --fork` mints a new identity), and after a merge the entry point must be `sync` rather than bare `check`, because `check` reads exports and a stale cache hides everything.

## Negative knowledge

- [scope: enumerating unreconciled work after a git merge | confidence: high | evidence: vast-rain-4873] a high-water mark compared by timestamp silently drops every record node that was authored before the last reconcile but merged after it — the checker reports 0 unreconciled and 0 violations while the work is gone from the frontier permanently. Reachability in the causal DAG is the only sound test; wall-clock ordering is not, and a fleet of machines with skewed clocks widens the window.
- [scope: validating markdown that git may have merged | confidence: high | evidence: vast-rain-4873] a node body carrying a literal git conflict-marker block passes `check` at 0 violations, commits, and is then published to the append-only public mirror. A validator for files that a merge tool can write must reject conflict markers explicitly; no other invariant catches them.
- [scope: publishing to an append-only store from a branch | confidence: high | evidence: vast-rain-4873] nothing in the push path reads HEAD, so work can be published from a feature branch that is never merged, leaving nodes on a public graph with no local counterpart and no way to retract them cleanly. Anything that writes to an append-only external store needs a branch and dirty-tree guard.

## Provenance

- vast-rain-4873 — the investigation that opened this gap: three reproduced defects and three Operator bets
