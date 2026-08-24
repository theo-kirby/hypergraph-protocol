---
node_id: 99accf1c-df19-5a8a-92bc-0c6a194561e3
slug: royal-light-0277
title: 'Read-through orientation shipped: hwm --impacts, tail replay, pressure trigger'
created_at: '2026-08-24T18:32:58+00:00'
parents:
- tender-ivy-4519
summary: ''
flywheel:
  node_id: a9592181-fcd5-5bc6-b7b7-d52212c586d0
  slug: white-silence-4441
  revision: 0
  pushed_at: '2026-08-24T18:36:56+00:00'
  content_sha256: cd037fb9333efafaf4e895cc56fd3088c37df5a859cdfa1e067300cec7a14ace
  parents_sha256: 08ffcedbf8d30ae6ecfabb57c155c15602b3b045040b6dc53740014af8e91fd9
  parents:
  - 14bdd467-d5e1-55dc-9c11-095a4d7f7e03
---
## What

Shipped the decision in `tender-ivy-4519` end to end: one new SPEC subsection, one
new CLI flag, three skill edits, one test, changelog under `[Unreleased]`.

## Why

The decision is a protocol change; until the spec says it, the skills do it, and the
CLI makes the tail printable in one command, orientation still reads only the
checkpoint and the reconcile trigger still lives in the operator's memory.

## Method

- **SPEC.md** — new subsection *Collaboration → Staleness and the reconcile
  trigger*: checkpoint/replayable-log framing, pressure trigger (~3-node threshold
  named as the orient skill's constant), default-branch-only recommendation, the
  two git-shaped consequences (branch visibility; never measure against a stale
  cache — export first).
- **tools/hypergraph.py** — `hwm --impacts`: the unreconciled listing gains each
  node's `## State Impact` lines verbatim (plus `(no ## State Impact section)` for
  epoch-legacy nodes), reusing `split_sections`; ~12 lines. Documented in
  docs/cli.md.
- **skills/hypergraph-orient** — workflow rebuilt around measure → replay →
  recommend: export before measuring (the cache is gitignored and stale right
  after a merge, exactly when the tail is fat), `hwm --impacts` for the tail,
  replayed deltas flagged pending-reconcile in the brief, and the three-way
  recommendation (default branch ≥3 → lead with reconcile-first; 1–2 → note and
  proceed; side branch/worktree → never recommend, note the fold-on-merge).
  Guardrails loosened one notch: `export` is now allowed (gitignored cache only);
  `new`/`update` still forbidden, and orient itself never reconciles — it
  recommends.
- **skills/hypergraph-reconcile** — the pressure trigger added as the first listed
  reason to run.
- **skills/hypergraph-dispatch** — workflow step 1: a coordinator on the default
  branch reconciles before cutting lanes when the trigger fired, so N lanes don't
  each replay the same stale tail; inside a lane the never-reconcile guardrail is
  unchanged.
- **tests/test_sync.py** — `test_hwm_impacts_prints_the_replayable_tail`: grafts an
  unreconciled node onto the clean fixture, asserts deltas appear only under
  `--impacts`.

## Result

387 passed, 2 skipped (was 386 passed — the one addition is the `--impacts` test).
`hwm --impacts` verified against this repo's live graph: tail was 0 at
implementation time, listing rendered correctly. Skill edits are live from the
next session, not this one (skills load at session start). The `≥ 3` threshold is
deliberately a skill-text constant, not protocol — the open measurement, which
belongs to the protocol benchmark, is at what tail length replay-orientation
degrades below reconciled-orientation.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 9d46d5394ae0143dfa25a4b52e62b727b3c3a076

## State Impact

- target: soft-hill-6082 — claim lands: SPEC gains Collaboration → Staleness and the reconcile trigger; orientation now reads through the checkpoint by replaying the tail's declared deltas, so HWM staleness no longer means orienting stale
- target: dry-wildflower-2260 — orient measures (export + hwm --impacts) and replays the tail, recommends by tail size and branch; reconcile lists the pressure trigger first; dispatch coordinators reconcile before cutting lanes; orient is no longer strictly read-only (gitignored cache export allowed)
- target: wandering-sun-8831 — new CLI surface: hwm --impacts prints each unreconciled node's State Impact lines, the replayable tail; +1 test (387 passing)
