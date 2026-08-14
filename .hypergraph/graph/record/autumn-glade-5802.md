---
node_id: 566d2f09-1cf3-5f2e-85ca-2da92014bd35
slug: autumn-glade-5802
title: A state node can be re-parented, and the mirror finds out
created_at: '2026-08-14T13:20:25+00:00'
parents:
- late-sage-5549
summary: ''
flywheel:
  node_id: 07bbab92-ad3f-510d-b621-70f401956689
  slug: soft-wind-9666
  revision: 0
  pushed_at: '2026-08-14T13:20:34+00:00'
  content_sha256: 2c4d8060aa1d16b224156f32d45943befddd43812d91ab7b114bf17dd1911dde
  parents_sha256: ff11761f7cd21b6308c04e8cf73f1ff30477307984c686958256939cef372012
  parents:
  - a0bc6040-7030-5f08-9b0d-6f7cd38fb8fe
---
## What

Closed the re-parent defect end to end: `hypergraph update --parent/--root`, a
`parents` push op executed as `nodes:add-parent` / `nodes:remove-parent`, and `parents`
moved from the strict-only verify field set into the default one. Proved on one node
against the live mirror before any batch — and the canary is what caught a wrong guard
in the new code.

## Why

`[rec: late-sage-5549]` states the defect. The short version: a pure re-parent produced
no mirror op at all, and the only check that would have noticed was opt-in. Nesting a
state node would have forked local topology from mirror topology silently and forever,
so this had to land before a single node moved.

## Method

Four changes to `tools/hypergraph.py`, plus one to `local_graph`:

1. **`hypergraph update --parent SLUG` (repeatable) and `--root`.** State nodes only —
   `cmd_update` already refuses record nodes outright, and that refusal is now the
   stated reason rather than a side effect: a parent edge in the record graph says
   "this happened after that", and history does not move. Validates that parents
   resolve, refuses a self-parent, a second root, and any edge that would close a
   cycle. `--reconcile` is still required (SPEC I3). `--body` became optional, so a
   pure re-parent is not forced to rewrite a body it is not changing.
2. **`parents_sha256`, a third sibling of `content_sha256`.** Over local *slugs*, for
   the reason `parents:` frontmatter holds slugs; the mirror ids that set resolved to
   live beside it as `flywheel.parents`, exactly as `flywheel.artifacts` is the
   path→id table next to `artifacts_sha256`. `push_plan` emits a `parents` op when the
   stamp and the local set disagree, with the same `or` clause the tag and artifact
   stamps carry so a *cleared* set is still expressible.
3. **`push_parents`, the one phase that cannot plan offline.** Measured against the
   installed CLI (0.1.108): `nodes:get` reports `has_parents` and **no parent ids at
   any projection**, core or full. So the mirror's current topology is knowable only
   from an export. The phase takes exactly one and re-derives the add/remove sets from
   it; the local stamp is only the trigger. Runs before tags, because an edge change
   bumps the child and a tag assignment locks against the revision in frontmatter.
4. **Transport methods** on both `FlywheelCliTransport` and `FlywheelRestTransport`,
   with all four optimistic locks re-read immediately before each call, add before
   remove, and a re-read-then-retry on 409 — never a blind retry.
5. **`local_graph` now detects cycles.** It is the validator `push_plan` already called
   before planning writes, and it only resolved slugs. Without this, a cyclic parent
   set gets as far as the host refusing the add — by which time half of a two-edge move
   has landed. The FakeTransport cycle guard is what exposed that ordering.

`VERIFY_FIELDS` gained `parents`, and the slug→mirror-id mapping that used to run only
under `--strict` became unconditional. A mirror-side parent is dropped from the
comparison only when it is a configured mirror root **with no local node claiming it**.

Tests: 337 pass (from 328). `FakeTransport` gained `add_parent` / `remove_parent`
modelling the four locks, the child-revision bump, host-side cycle refusal, and an
assertion that removing the last parent is unreachable. New coverage: a pure re-parent
plans a `parents` op and no body update; ordering is add-then-remove; a record-node
re-parent aborts the run; nothing detaches a node from every parent it has; a cycle is
refused before any edge is written; `verify` reports parent drift by default; the
first run after this ships stamps without writing an edge.

## Result

**The migration is a stamp, not a write.** On this repo's live mirror the first run
planned **87 parent sets and performed 0 edge writes** — the export showed every edge
already correct. That is the design and not luck: a stamp seeded from the local set
could not have told "never stamped" apart from "re-parented before stamping", so the
export is the authority and the local stamp is only the trigger.

**The live canary found a bug in the new code, and `push --verify` is what reported
it.** `retroactive-repair-5104` moved under `wandering-sun-8831`; the add landed, the
remove did not, and the node was left double-parented while the local stamp said
"done". Cause: the "never remove a mirror-root edge" guard exempted every configured
root *by id*. That guard is right for an adopted project, whose local roots hang off
freshly minted roots with no local counterpart — and wrong for a re-homed one like this
repo, which mirrors into the very roots its node files declare, so the old parent
`cool-king-8586` was itself the exempt id. Fixed to exempt only mirror roots with no
local counterpart, and pinned by
`test_a_root_edge_is_removable_when_the_mirror_root_is_a_local_node`. The re-run moved
the edge (`+0/-1`, the add having already landed) and both `push --verify` and
`push --verify --strict` return **0 drift findings**. Had `parents` stayed a strict-only
field, the default push would have reported success on a graph the mirror disagreed
with — which is the argument for the move, made by the defect it caught.

Two things the plan predicted that did not happen, recorded because the next round
should not go looking for them:

- **The byte-identical verify pin did not move.** The plan expected
  `test_verify_mirror_findings_are_byte_identical_after_the_refactor` to break, since
  it pins the default findings against a hand-rolled oracle that never compared
  parents. It did not, because the honest fix was upstream: `mirror_export_of` was
  emitting no `parent_ids` at all, which a real `export:subgraph` does emit. Making the
  fixture faithful was the correct change and it left the finding set untouched.
- **A re-parent bumps the *parent's* revision too**, not only the child's. That is not
  in `backend/flywheel.md`, which only warns about the child. It surfaces as one
  revision-skew finding per touched parent and is absorbed by the existing
  verify-then-resync loop in `cmd_push`, which converged to 0 on the same run.

## Repo cost

`tools/hypergraph.py` +~230 lines; `backend/mirror.md` gained a § Topology section and
a rewritten § Verification; `backend/flywheel.md`'s re-parent section now says what
implements it and that `nodes:get` cannot answer the question.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 437fcee23bf6395e0ac3615644febb32b3e2821d

## State Impact

- target: wandering-sun-8831 — `update --parent/--root`, the `parents` push op, cycle detection in `local_graph`; 337 tests
- target: empty-forest-6305 — push moves parent edges: nodes:add-parent/remove-parent, the export as the authority on topology, and `parents` as a default verify field
- target: retroactive-repair-5104 — the live canary that proved it, and that caught the mirror-only-root guard bug
- target: protocol-benchmark-4417 — one more instance of the pattern the benchmark is about: an unmeasured category was invisible until something measured it
