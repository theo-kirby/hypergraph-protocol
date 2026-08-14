---
node_id: 77822bc1-cefa-579a-9f3d-b36f1deed139
slug: early-mesa-8507
title: 'heal tags on a live mirror: 188 nodes recovered, and the three defects that took'
created_at: '2026-08-10T06:48:08+00:00'
parents:
- clear-moss-4527
summary: 'The live run on neural-whoop completed: 22 definitions, 486 assignments across 188 of 189 nodes, counts identical to the archive, push --verify 0 drift, archive untouched at revision 28. Three host behaviours no fake had modelled: tags:create returns the root node not the tag (the no-guessing guard caught it after one create, and resolve-by-name recovered), cluster:* tags must stay a connected set at every write (so assignment order is part of the contract), and creating a tag bumps every node''s revision (so nodes nobody wrote read as drift). All three fixed with tests before the run resumed; the healer framework itself did not change.'
flywheel:
  node_id: 1921bda8-9fa4-5e4a-9e85-1d7418f1210a
  slug: small-smoke-5943
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: b1a12b55d37455fe02e162e271918f51114bceb05e586a7fbec5af3363b2cbfe
  parents_sha256: 00a11623110260e228c1238691af29e9b6b1f7b725e03f6e7a7afea374fffc75
  parents:
  - 59e2de70-35eb-585a-88bf-bfe40af28a7b
---
## What

`hypergraph heal tags` ran against neural-whoop's live mirror and completed:
**22 tag definitions created, 486 assignments across 188 of 189 nodes, per-tag counts
identical to the archive, `push --verify` 0 drift, a second `heal tags` finding
nothing, and the archive root still at revision 28.**

Getting there took **three defects, none of which was findable by reading** — the
mirror half had only ever met `FakeTransport` [rec: clear-moss-4527], and every one of
these is a host behaviour that no amount of care about the code would have surfaced.

## Why

The whole point of a heal is the repo it was built for. An offline trial on a *copy*
proved the local half; the mirror half was the claim still outstanding, and it is where
all three defects lived.

## Method

Offline half, then online half, with a preflight and a commit between them. Each defect
was fixed in the protocol tooling with a test **before** the run was resumed, so the
mirror never absorbed a workaround.

## Result

### Defect 1 — `tags:create` returns the root node, not the tag

The response is the updated *graph root*: `content`, `artifacts`, `graph_projection`,
`can_write`, and no `tag_id` anywhere in it.

**The guard worked exactly as designed.** `_parse_tag` refused to guess an identity and
aborted after **one** creation — leaving one tag on the mirror, zero local stamps and
zero assignments. Because the vocabulary is reconciled **by name**, the resumed run
*found* that orphan and adopted it instead of minting a second: the duplicate-definition
failure this whole feature is built to prevent was one blind `except` away, and did not
happen.

Fix: identity comes from re-reading the root and resolving by name — the same read that
already supplies the bumped root revision. The doctrine "never trust a mutating response
for a fact you can read authoritatively" was already written down for revisions; it
simply had not been applied to ids.

### Defect 2 — a `cluster:*` tag must cover a *connected* set, checked on every write

A 422 naming a specific disconnected node. Measured on the archive: **all eleven
`cluster:*` tags are connected and all eight `kind:*`/`outcome:*` tags are freely
disconnected** (`kind:experiment` is in 12 components), so the rule follows the name
prefix and nothing else.

The trap is that the *final* set is connected and the write still fails: an atomic
per-node replace builds the set one node at a time, and any gap mid-way is rejected.
**Assignment order is part of the contract.** `assignment_order()` grows every
constrained tag outward from a single node — a spanning-tree traversal — respecting all
of them at once, and seeded by **what the mirror already holds**, without which a
resumed run derives an order that is valid from empty and wrong from where it actually
is. Simulated against the real graph before any write: 188 ordered, 0 blocked, 0
connectivity violations at any prefix.

### Defect 3 — creating a tag bumps the revision of *every node in the graph*

The largest, because it breaks an assumption rather than a call: **a node's revision
can move without anyone writing that node.** 22 creations moved all 196 nodes —
untagged ended at 22, tagged at 23 (their own assignment), the four assigned twice at
24.

Two consequences, and the second is the expensive one:

- Every revision held across a creation is stale, so all 188 assignments locked against
  an invalidated revision. They only succeeded at all because an atomic replace may be
  retried — the retry-doctrine inversion, written down as doctrine [rec: clear-moss-4527],
  silently carried the entire run.
- Six **untagged** nodes were left reading as revision drift. That is the
  188-false-drift-findings failure this feature was explicitly built to avoid,
  arriving by a route nobody predicted: not from failing to fold what we wrote, but
  from the host moving nodes we never wrote.

Fix: `resync_mirror_revisions()` from one export per root, run *before* assigning (so
the locks are current) and again at the end. And because a stale stamp left by an
earlier run would otherwise never be repaired — a push only writes what changed —
`push` now converges from the export `--verify` already fetches: no extra request,
revision only, then a re-verify to prove it converged rather than to hide it.

### What held

- **`origin:` was never a write target.** `heal_write_targets()` passed on all 212
  pushed nodes, and the archive root is still at revision 28.
- **Append-only held.** `push --plan` after the offline heal: 0 creates, 0 body updates,
  0 violations, 188 tag ops.
- **Idempotence held.** A second `heal tags` reports 0 nodes would change.
- **Dry run held.** Every `--apply`-less invocation wrote nothing.
- **Fidelity is exact.** Per-tag assignment counts on the mirror match the archive.

## Assessment

The framework's shape survived contact; only its assumptions about the host did not.
Nothing about `Healer`, `detect`/`apply`, the registry, or the drift types changed
across three defects — every fix landed in the transport or in `push_tags`. That is
the first real evidence for the extensibility claim, and it is better evidence than a
second healer would have been, because it was not designed for.

`FakeTransport` now models all three behaviours, so they are regressions rather than
anecdotes. The fake was not *wrong* before — it was optimistic in exactly the places a
real host is not, which is the general lesson: a fake models the protocol you wrote
down, and a live run tests the protocol the host actually implements.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: ca2d301ac5f60ef5587158cc58422976298f4edb

## State Impact

- target: retroactive-repair-5104 — Closed: heal tags is proven end to end against a live mirror, not only FakeTransport. 22 creations, 486 assignments, 0 drift, archive untouched, idempotent on a second run. Status working.
- target: empty-forest-6305 — Three live-host behaviours are now handled and tested: tags:create returns the root node so identity comes from a re-read by name; cluster:* tags need a connectivity-safe assignment order seeded from what the mirror holds; and creating a tag bumps every node in the graph, so push converges stale revisions from the export verify already fetches.
- target: blue-sun-8921 — Op 10's contract gains two host constraints worth stating: a backend may constrain *where* a tag lives (a connected node set), and a tag creation may move revisions graph-wide — so a node's revision can change without that node being written.
- target: bitter-sound-9744 — The sixth field defect is repaired in the field, not just in the tooling: neural-whoop has its taxonomy back, and is the evidence that an adoption is not write-once.
- target: fair-field-3265 — A fake models the protocol you wrote down; a live run tests the protocol the host implements. FakeTransport was not wrong, it was optimistic in the three places a real host is not.
