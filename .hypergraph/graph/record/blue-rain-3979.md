---
node_id: 25146fc4-8113-51cc-b944-32cbc7a60e00
slug: blue-rain-3979
title: 'The mirror split: offline commands never import the network half'
created_at: '2026-08-16T17:55:18+00:00'
parents:
- violet-shade-9541
summary: ''
flywheel:
  node_id: ac88d89a-37df-5716-b350-bc947c95068a
  slug: mute-hill-5406
  revision: 0
  pushed_at: '2026-08-16T18:24:57+00:00'
  content_sha256: 1f81e7d1729e63735fee5ff02ce293b0c88b20d1b4288627ab782c88c889a979
  parents_sha256: f60fcd0870036f71cba53d59314076ccbfff6bfa478cc036b51dd8c6f18666e8
  parents:
  - 7a839acb-23ac-5abc-b0a7-a06f180beaba
---
## What

Split the mirror's networked half out of `tools/hypergraph.py` into a sibling
module, `tools/hypergraph_mirror.py` (2,487 lines; core drops to 6,025 from
8,376 pre-fold). The cut sits at the **network boundary, not the word
"mirror"**: everything that resolves a credential, looks for a binary, or opens
a socket moved (errors, `MirrorNode`, both transports, `make_transport`,
`PushJournal`, `Pacer`, `execute_push` and the pushers, `verify_against_mirror`,
`mirror_session`, `mirror_doctor`, `run_mirror`, `mint_mirror_roots`,
`mirror_pull`, and `cmd_push`'s executing tail as `run_push`). The offline
mirror *bookkeeping* stayed in core — `push_plan`, `verify_mirror`,
`apply_push_results`, legend/lineage, `file_sha256` — because
`push --plan/--verify --against/--record-result/--legend/--lineage` must work
with no mirror module present, as do the config/git gates `mirror_configured`,
`mirror_root_ids`, `publish_branch`, `publish_branch_block`.

Core gains `_mirror()`: a spec-loader that registers the running core module as
`hypergraph_core` *before* exec, so the sibling's `import hypergraph_core as
core` binds to the same object under all three names core runs as (`__main__`,
`hypergraph_protocol`, test fixture) — no forked class identities;
`MirrorError` still subclasses core's `LocalGraphError` across the boundary.
Mirror code reads patchable core symbols as `core.<attr>` (never from-import),
so existing monkeypatches keep working. Five seams: `cmd_push` keeps its
offline modes and transport-free stand-downs then delegates to `run_push`;
`cmd_sync` unchanged (lazy via `cmd_push`); `heal_session`; the tags heal's
mirror phase; `adopt --pull`. `cmd_mirror` is a 2-line stub.

Folded incidentals: the two mis-placed section banners fixed (`upgrading`
banner moved above the skills/upgrade functions it describes; a new `heal
driver` banner separates the generic driver from healer 2), and the shadowed
duplicate `_load_export_nodes` deleted.

## Why

The docstring has promised "these commands never touch the network" since the
mirror landed, enforced only behaviorally (a monkeypatched `make_transport`
that explodes). The split makes the promise **structural**: an offline command
cannot reach network code that is not in its process. It also honors the
packaging story — the wheel now ships two files (`hypergraph_protocol.py` +
`hypergraph_protocol_mirror.py`), no dependency change, no new script: the
mirror module has no PEP 723 header and refuses direct execution.

## Method

Mechanical extraction by script: cut the contiguous block, then rewrite bare
references with a `core.` prefix using `symtable` + `ast` (only `ast.Name`
loads touched — never strings, comments, attributes, or kwarg keys; 104
references on 103 lines; zero stores of core names, confirming the block never
mutates core globals). `tests/graph_fixtures.py` loads the sibling through
`hg._mirror()` itself — the loader is under test on every run — and re-exports
its symbols onto `hg` for the ~186 existing reads; the 7 transport/pacer/doctor
patch sites moved to `hgm`. `mirror_root_ids` now raises `LocalGraphError`
(core cannot name `MirrorError`); two tests that expected `MirrorError` from it
now expect the superclass.

New tests (tests/test_mirror_split.py): offline commands never import the
mirror module (subprocess-probed: export, check, push --plan, mirror-less
push); `_mirror() is hgm` and `hgm.MirrorAuthError` is caught by
`except hg.LocalGraphError`; wheel/sdist ship the module under the names
`_mirror()` looks for; the module is not a script.

## Result

`uv run pytest tests/` — 293 passed, 2 skipped (289 + 4 split tests). `uv
build` succeeds; the wheel lists both `hypergraph_protocol.py` and
`hypergraph_protocol_mirror.py`. Manual smoke: `push --plan` runs offline and
reports the 2 pending creates. Line counts: core 6,025, mirror 2,487.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 6b66c307c6fcb6020e23b3cb63bb956d3fff2aae

## State Impact

- target: wandering-sun-8831 — the implementation is now two files: core (offline, 6,025 lines) + a lazily-loaded mirror module (2,487 lines); the no-network promise for offline commands is structural, held by a subprocess test; suite 289→293
- target: empty-forest-6305 — the mirror's networked half lives in tools/hypergraph_mirror.py (installed as hypergraph_protocol_mirror.py), loaded only by push/sync/mirror/heal-mirror-phase/adopt --pull; offline mirror bookkeeping (push --plan, --verify --against, --record-result) stays in core
