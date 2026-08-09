---
node_id: 38413a82-1858-5e14-877b-c4c08f4bee7e
slug: sweet-aspen-3667
title: 'Mirror push blocked: the Flywheel mirror is not on the current key’s account; preflight now proves write access'
created_at: '2026-08-09T09:57:16+00:00'
parents:
- sweet-wave-7885
summary: ''
flywheel:
  node_id: a5a73589-6761-5e93-96fa-109719deeda4
  slug: ancient-math-5027
  revision: 0
  pushed_at: '2026-08-09T10:16:22+00:00'
  content_sha256: 452bf4260839d51820340a164fbcd217a91bca6b4170e5592bc6e4dfde7e589a
---
## What

Attempted the reconcile's mirror step (skill step 8) and found two things — one a
defect in the lab, one a fact about the project's Flywheel mirror.

**The mirror is unreachable from the current key, and nothing was written.** The
17-op plan (9 creates, 8 updates) failed on every op. The account is back to
exactly the 458 nodes it started with, verified before and after; `push
--record-result` was never run, so no `flywheel:` frontmatter changed. The local
graph is untouched and remains canonical.

**Preflight was blessing a key that could not write.** It checked the account was
reachable and countable — both reads — and reported 21/21. Arm B's entire job is
writing nodes. Fixed: `flywheel_can_write` creates a labelled probe node and
deletes it, and the check runs on every arm-B key in both the per-run and
shared-account paths.

## Why

Follows `sweet-wave-7885`. The Operator asked for everything to be synced and
pushed — git and Flywheel both — before parking the thrust.

The write gap is the same class of defect as P1/P5 on the first run, and it is
worth naming as a pattern rather than an incident: **a check that exercises a
different capability than the run needs is not a check.** `BOXLAB_PROVISION_OK`
proved a script reached its last line, not that the memory system worked. A node
count proves an account can be read, not that it can be written. Both passed
while the thing they stood for was broken.

## Method

Executed `hypergraph push --plan` (17 ops, 0 violations) against the Flywheel MCP
over JSON-RPC. Every create returned `403 auth_error: Only users with write access
may perform this operation`; every update returned `404: Not Found`.

The 403 initially read as a read-only key. The write probe refuted that: with
`parent_ids: []` the same key creates and deletes a node cleanly. So the 403 is
about the *parents* — the mirror's nodes — not about the key.

Confirmed by three reads:

- `flywheel_get_node` on the mirror state root `9e687be1-1c80-56a2-bc0c-d4476edc0a2e`
  (`cool-king-8586`) → **404: Not Found**.
- `flywheel_resolve_node_slug cool-king-8586` → **`status: not_found`**, no candidates.
- Paged all 458 visible nodes: **0** are this project's. They are the FIFA World
  Cup and other unrelated past-project graphs the first run's forensics found.

So the mirror this project pushed to is not on the account the current
`FLYWHEEL_API_KEY` belongs to.

## Result

Git is fully synced; Flywheel is not, and cannot be from here.

- **Git: complete.** 22 commits pushed to `origin/main` as a fast-forward — the
  history rewrite only touched unpushed commits, so no force push was needed.
  Working tree clean. `hg-viz/` is now ignored: it is a worktree with its own
  `.git` file, and a `git add -A` from the main tree would have committed a second
  full copy of the repo.
- **Flywheel: blocked, cleanly.** Nothing partial was written. Because the mirror
  is a regenerable projection and the local files are canonical, nothing is lost —
  once the right account is identified, `push --plan` regenerates the whole mirror
  from scratch.
- **Preflight now proves write access.** 162 tests pass, three of them holding the
  probe honest: a read-only key fails the check, the probe deletes what it
  creates, and a probe that cannot be deleted still passes but reports the node id.
- Verified live: probe created and deleted, account back to 458.

Unresolved, and needing the Operator: which Flywheel account holds the
hypergraph-protocol mirror. Either the rotated key is for a different account, or
the mirror was removed. Both are recoverable; neither is guessable from here.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 52bb63cf8f49d5737a8dfcef264d01ae57042349

## State Impact

- target: protocol-benchmark-4417 — preflight had a gap of exactly the kind it exists to close: it verified the Flywheel account was READABLE (reachable, countable) and reported 21/21 for a key whose write capability was never exercised. Arm B's entire job is writing nodes, so a read-only key would have produced three runs that recorded nothing and a launch preflight had blessed. Fixed: `flywheel_can_write` creates a labelled probe node and deletes it, run against every arm-B key in both the per-run and shared-account paths, and verified live (probe created and deleted; account back to exactly 458). 162 tests pass.
- target: empty-forest-6305 — the Flywheel mirror is UNREACHABLE from the current FLYWHEEL_API_KEY and could not be refreshed. The 17-op plan (9 creates, 8 updates) failed on every op; nothing was written and the account is back to exactly its 458 starting nodes, with `push --record-result` never run, so no `flywheel:` frontmatter changed and the local graph is untouched. Diagnosis, from three reads: `get_node` on the mirror state root 9e687be1-1c80-56a2-bc0c-d4476edc0a2e (cool-king-8586) returns 404, `resolve_node_slug cool-king-8586` returns not_found with no candidates, and 0 of the 458 visible nodes belong to this project. The mirror is not on the account the current key belongs to — either the key was rotated into a different account or the mirror was removed. Nothing is lost: local files are canonical and the mirror is a regenerable projection, so `push --plan` rebuilds it once the right account is identified. Needs the Operator.
- target: fair-field-3265 — the pattern behind three separate failures, now named: a check that exercises a different capability than the run needs is not a check. BOXLAB_PROVISION_OK proved a script reached its last line, not that the memory system worked. A node count proves an account can be read, not that it can be written. Both reported success while the thing they stood for was broken. A gate must exercise the capability under test, and when a service offers no scope introspection that means performing the real operation and undoing it.
