---
node_id: 55641cfe-7b2e-5e96-a6da-baa2604fa5ed
slug: vast-rain-4873
title: 'Parallel work: the record/state split is already the fork/merge split — three defects reproduced'
created_at: '2026-08-09T12:03:36+00:00'
parents:
- calm-sand-3399
summary: 'Design investigation into worktrees, branches, forks, PRs and cloud fleets. Reproduces three defects (timestamp HWM silently drops merged nodes, conflict markers pass check, push has no branch guard) and records three Operator bets: maintainer-reconciles-on-main, CI fails a PR with no record node, mirror publishes from CI on main only.'
flywheel:
  node_id: 33be9687-071a-5ef3-baf8-dec744dc7c51
  slug: little-lake-5014
  revision: 0
  pushed_at: '2026-08-09T12:03:41+00:00'
  content_sha256: 7cd6569c49f345a3826570c0fd8e8a04fa421f391ef4c1035cf753a34f545d34
---
## What

A design investigation into how Hypergraph behaves when more than one person or agent
works a repo at once — worktrees, branches, forks, PRs, and cloud fleets — plus the
Operator decisions that came out of it. **Three defects were reproduced, not theorised.**
No protocol or tool change is made here; this node opens the gap and records the bets.

## Why

Every workflow so far has been one writer on one machine. The next projects will not be:
the Operator on a laptop, several cloud agents in parallel, and outside contributors who
fork a public repo and open a PR without any access to it. Before initializing bigger
projects on the protocol, the question is what the two-graph discipline gives for free in
that world and where it silently loses work.

The framing that came out of it is that **the record/state split already is the
fork/merge split**, and it was not designed for that:

- The record graph is append-only, one file per node, so two branches produce two new
  files and merge with zero conflicts, always.
- The state graph is single-writer by I3, so concurrent branches edit the same files.

That yields the collaboration rule directly from the invariants rather than from new
machinery: **contributors record; the maintainer reconciles.** A PR carries facts, main
carries claims.

## Method

Reproduced each defect against a throwaway graph minted with `adopt --init`, then
inspected the relevant code paths in `tools/hypergraph.py`.

1. **HWM.** Minted two record nodes with `--created-at` skewed to imitate a branch that
   started before main's last reconcile: Bob at 09:30 on a branch, Alice at 10:00 on
   main. Set `high_water_mark: alice-node-0002`, exported, ran `check`.
2. **Conflict markers.** Pasted a literal `<<<<<<< HEAD` / `=======` / `>>>>>>> branch`
   block into a record node body, re-exported, ran `check`.
3. **Push guards.** Grepped the whole push path for `branch`, `dirty` and `HEAD`; read
   step 7 of the reconcile skill, which calls `push` unconditionally.
4. **Partial merge.** Rewrote a record node's `parents:` to a slug that does not exist,
   imitating a cherry-pick whose causal parent stayed behind.

## Result

**1. The high-water mark silently deletes merged work.** `check_hwm` enumerates
unreconciled nodes by timestamp — `created > cutoff` — with no ancestry test. Bob's node,
stamped earlier but merged later, was never folded, and the checker reported
`0 unreconciled record node(s)` with `0 violation(s), 0 warning(s)`. The work is gone from
the frontier permanently and nothing anywhere says so. This fires on **every** merge of a
branch that began before the last reconcile, which is every parallel workflow. Clock skew
across a cloud fleet widens the window.

**2. Git conflict markers pass the checker.** A node body carrying the full marker block
checks 0/0, commits, and is then published to the public mirror.

**3. `push` has no branch or working-tree guard.** Nothing in the push path reads `HEAD`.
An agent on a feature branch can publish nodes to an append-only public graph; rejecting
the PR afterwards leaves them there with no local counterpart.

**4. Two things behaved correctly and are worth keeping.** `export` refused the dangling
parent by name. And slug collisions across branches surface as a git add/add conflict,
because filename = slug — which matters because `node_id = uuid5(slug)`, so a silent
collision would be an identity collision.

**A fourth defect found by reading, not yet reproduced:** an outside contributor inherits
the committed `mirror:` key, so reconcile step 7's unconditional `hypergraph push` exits 2
on a machine with no credentials. The exit-0 no-op guarantee covers *no mirror configured*
but not *a mirror that is not mine*.

**Operator decisions (bets, immutable):**

- **Reconcile is maintainer-on-main only.** Contributors and cloud agents record only.
  One pass folds every merged branch at once — better than N sequential passes, because
  the librarian sees the whole batch and writes one coherent claim.
- **CI enforcement fails the PR.** `check --since <ref>` reporting "code changed, no
  record node" as a red check is the only mechanism that reaches contributors who never
  read AGENTS.md. Opt-in per repo.
- **The mirror publishes from CI on main only.** The mirror is a build artifact of the
  default branch, like a docs site. Credentials live in one repo secret; contributors and
  cloud agents never hold them, which preserves the invisibility won in calm-sand-3399.

**Also noted for the design, not yet acted on:** `check` reads exports, so a stale
`.hypergraph/cache/` after a merge hides everything — post-merge the entry point must be
`sync`, never bare `check`. And "fork" means two different things (a GitHub repo fork
keeps the same graph and the same slugs; `import --fork` mints a new identity), which an
agent will confuse.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e93df94ec732ba1613b363be8ca6baa052e04184

## State Impact

- target: NEW collaboration — Open the gap: parallel and multi-contributor work under the protocol. Carries the maintainer-reconciles rule, the three reproduced defects, the three Operator bets, and the repo-fork/graph-fork distinction.
- target: young-wave-9364 — I5 specifies the high-water mark as a timestamp cutoff; a merge-aware protocol needs an ancestry frontier. Doctrine to add: contributors record, maintainers reconcile.
- target: wandering-sun-8831 — Two reproduced checker defects: HWM enumeration by timestamp loses merged nodes silently, and git conflict markers in a node body pass 0/0.
- target: empty-forest-6305 — push has no branch or dirty-tree guard, and exits 2 rather than no-op when a mirror is configured but the credentials are not the owner-s.
- target: dry-wildflower-2260 — reconcile-s unconditional publish step is correct for the maintainer and wrong for a forking contributor; it needs a publish-branch gate.
