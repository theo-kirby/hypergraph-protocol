---
node_id: aae9a850-16f7-5088-827e-06893a4b0f02
slug: careful-harbor-3902
title: 'M2: push --verify + mirror slug legend; first live verify caught four real drifts'
created_at: '2026-08-07T20:16:27+00:00'
parents:
- shady-quill-2790
summary: push --verify (read-only mirror drift check, exit 1) + push --legend (mirror-only slug legend node). First live run caught 3 silent manual-push deviations + 1 double-scaffolded state body; all repaired, guard added, verify clean. 60 tests green.
flywheel:
  node_id: da12e9f7-dd2f-5666-a942-e390000d59fe
  slug: purple-sunset-9437
  revision: 0
  pushed_at: '2026-08-07T21:20:13+00:00'
  content_sha256: 354e7c50bc5c0ed323840e12dd7f3d0595c2f9538513e10d14d6d0a0f5d1cc19
---
## What

Built mirror drift detection and the slug legend (adoption thrust M2): `hypergraph push --verify --against <flywheel-export.json>` (read-only diff of a fresh mirror export vs the local node files, exit 1 on drift) and `hypergraph push --legend` (body of a dedicated mirror-only legend node mapping local↔flywheel slugs) — then ran the first live verify against this repo's own mirror, which immediately caught four real drift defects, all repaired.

## Why

The mirror is a one-way projection whose sync detection (`push --plan`) compares local bodies against frontmatter stamps written from those same local bodies — so a manual MCP push that deviates from the plan bytes is undetectable from the local side. vast-sky-3964 called for real drift detection before adopter repos start depending on mirrors, plus a legend so mirror readers can resolve locally-minted provenance slugs.

## Method

`verify_mirror` diffs both graphs against a single export (fetched with one `flywheel_export_subgraph` over both mirror roots): local nodes never pushed or missing from the export, body-hash mismatches (re-hashing remote content, not trusting frontmatter), summary mismatches, pending local edits, revision skew; mirror nodes with no local counterpart. The legend node (title exactly "Hypergraph mirror slug legend") lives only on the mirror, parented to the mirror record root, regenerated each push by the skill layer; `import` and `verify` exclude it by title so byte-identity of real nodes is never touched. Reconcile skill step 8 extended: push → legend → fetch export → verify. Five new tests (clean mirror, each drift kind, legend exemption + unpushed graph, legend content, import skip).

## Result

60/60 tests green. The first live run was a genuine shakedown: `push --verify` exited 1 with five findings — one expected (the M1 node not yet pushed) and four real defects invisible to `push --plan`: (1) green-field-8645's mirror copy was pushed without its trailing newline, (2) bold-field-1268's without a mid-document blank line, (3) empty-forest-6305's summary was never updated on the mirror, all three from earlier manual MCP pushes deviating from plan bytes; (4) the local morning-crane-7863 body had `Status:`/`## Current` scaffolding duplicated — the M0 reconcile passed a fully-templated body to `hypergraph new state`, which wrapped it again, and `check` cannot see nested duplication. Repairs: local body fixed via reconcile-gated `update`; all three mirror copies re-pushed byte-identical (lease → commit → release); legend node created live (mirror slug divine-term-6563); verify now exits 0 and the push plan is empty. Countermeasure landed: `new state` now rejects a `--body` that already starts with `Status:` or contains template headings, exit 2 before writing. Commits 6086ae5, f6ce715.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: f6ce715b7dd0826b127c3b56edd9a5b14c3ab0ce

## State Impact

- target: morning-crane-7863 — M2 done: verify + legend built, live-proven; milestone list advances to M3
- target: wandering-sun-8831 — new claim: push --verify and push --legend subcommands; new-state pre-scaffolded-body guard; test count 60
- target: empty-forest-6305 — new claim: mirror drift detection + slug legend close the projection-trust gap; new negative knowledge: push --plan cannot detect manual-push byte deviations (frontmatter is stamped from local bytes) — only verify against a fresh export can
