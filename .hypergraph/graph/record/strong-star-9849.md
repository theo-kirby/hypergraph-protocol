---
node_id: 106bb76e-9d77-5de2-b871-ef4d18d39f40
slug: strong-star-9849
title: 'Named views: the state graph generalized to N derived graphs (0.0.13 feature)'
created_at: '2026-08-19T10:23:23+00:00'
parents:
- witty-summit-9656
summary: 'Named views shipped: view-qualified impacts, per-view reconciliation, views ls/add, per-view render; state graph internally becomes view #1; back-compat pinned by goldens and confirmed against the real 0.0.12 CLI.'
flywheel:
  node_id: 93f06f70-f526-5acb-beb8-2cc83386149d
  slug: plain-union-1511
  revision: 0
  pushed_at: '2026-08-19T10:25:52+00:00'
  content_sha256: cb07f80da09e97eb835bb42f8c41c503ac6d4318271d10395e11cb2417c30386
  parents_sha256: 381f05cf081126bf3d4c94a5d7ec7390d63e16fd41102db810151baae75c0523
  parents:
  - 3401b72d-8c7b-514f-a48a-404b70bc3aa6
---
## What

Implemented **named views** (v0.0.13): a project can now keep N derived graphs over
the record graph beside the state graph — `hypergraph views add policy` declares one,
record nodes reach it with view-qualified impact targets (`policy/<slug>`,
`policy/NEW <kebab>`), and each view reconciles independently under its own
high-water mark. Internally the state graph became "view #1": one config-derived
enumeration (`graph_kinds(config)`), one node template, one checker path.

## Why

The state graph was the protocol's only projection, so a project with a second axis
worth distilling (the motivating example: an RL project tracking policy evolution)
had to overload it. Mathematically each state node was already a family of
hyperedges over record vertices — one projection over an event log — so
generalizing to N named projections is the same construction, not a new one.
Design decisions were made with the Operator: the name "views", the
`view/target` impact grammar with unqualified meaning state (so all 106 existing
immutable record nodes stay valid), the state-node template verbatim for view
nodes, record as sole ground truth (views cite record nodes only; view-over-view
provenance is not representable), and the state graph staying the privileged,
mandatory view.

## Method

Eight phases, each keeping the suite green and this repo's `sync` byte-identical:
(1) config-derived kinds — `view_defs`/`graph_kinds` helpers, every
pair-hardcoded site that holds a config converted to a loop, `GRAPH_KINDS`
surviving only as the no-config fallback; (2) grammar — `parse_impacts` splits the
target on the first `/` *before* the NEW test and returns `(view, target, delta,
is_new)`; (3) checker — `run_check` loads each configured view's export as a
sibling of `--state`, loops `check_state_nodes`/`check_hwm` per view, filters the
pending-impact tally by view, and reports an impact naming an unconfigured view
as an I2 violation; (4) CLI — new `views ls|add` (root minted through
`create_root_node`, HWM seeded with the current record tips so a late-born view
starts caught up, config block appended textually), `new`/`update` generalized to
view kinds behind the same `--reconcile` gate and body-hash CAS, `hwm --view`,
`export`/`sync` over all kinds; (5) render — `render_state(view=…)`, `render
--view`, view snapshots beside STATE.md; (6) SPEC Views section + I2/I3/I5
generalized per view, templates, skills, INTERFACE/README/CHANGELOG/docs;
(7) tests — `tests/test_views.py` (goldens pinning viewless behavior
byte-for-byte, grammar cases, per-view HWM, end-to-end scratch project), fixtures
`views-policy`, `violations/{i2-unknown-view,i5-view-hwm}`, per-view ancestry
variants in test_collaboration; (8) this record + reconcile.

Verified end to end in a scratch project: `adopt --init` → `views add policy
--md POLICY.md --reconcile` → record node with `policy/NEW ppo-baseline` impact →
`new policy … --reconcile` → `sync` exit 0 with `cache/policy.json` and POLICY.md
rendered.

## Result

386 tests pass (332 before; the new coverage is views). This repo's own `sync`
stays exit 0 with STATE.md byte-identical — a viewless project is untouched by
construction, pinned by golden tests over the clean and local-graph fixtures.
Back-compat confirmed against the real old CLI: `uvx --from
hypergraph-protocol==0.0.12 hypergraph check` over a views-using graph reports
the qualified impact line as an I2 unparseable-line violation (the one honest
exception, documented in CHANGELOG and SPEC: a project that adds views needs
≥0.0.13 tooling; bare projects are unaffected in both directions). The mirror
deliberately stays record+state — views are rebuildable projections, and `push`
prints one line noting the skip. Out of scope for v1, stated in SPEC: per-view
tag vocabularies and status vocabularies, view-over-view provenance, orient
reading views, dispatch targeting views, `views rm`/rename, import of view
graphs.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e05b6b80e1f363f0916f6606dd0e682672567e58

## State Impact

- target: soft-hill-6082 — generalized: the state graph is now view #1 of N named views over the record graph; the live hypothesis (single-writer distillation) now has a per-view formulation and a second axis to test it on
- target: young-wave-9364 — SPEC gains the Views section; I2 grammar adds view-qualified targets, I3 becomes single-writer-per-view, I5 becomes per-view reconciliation frontiers; invariant numbers unchanged
- target: blue-sun-8921 — node-file format unchanged (additive promise held against real 0.0.12); config gains a write-once views: block, exports gain cache/<view>.json, node files gain graph/<view>/ directories
- target: dry-wildflower-2260 — record teaches view-qualified impacts, reconcile folds per view and owns views add, orient states the state graph stays the cold-start read, init states views are post-init
