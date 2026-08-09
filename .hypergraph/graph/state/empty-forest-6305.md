---
node_id: be944979-3508-5583-b6b8-bd96106ca7f5
slug: empty-forest-6305
title: Git-native backend
created_at: '2026-08-07T10:57:13.256136+00:00'
parents:
- cool-king-8586
summary: 'Git-native backend live: node files source of truth, Flywheel a regenerable mirror; push --verify + slug legend close the projection-trust gap.'
flywheel:
  node_id: be944979-3508-5583-b6b8-bd96106ca7f5
  slug: empty-forest-6305
  revision: 4
  pushed_at: '2026-08-07T21:24:20+00:00'
  content_sha256: 004f92e6b11ad52a830ea01836d0fd2ae3b90455cd854784f4e515d93147aaa5
---
Status: working

## Current

- The git-native backend exists and is this repo's live backend: markdown node files under `.hypergraph/graph/{record,state}/<slug>.md` are the source of truth, with `backend/local-adapter.md` mapping all 10 INTERFACE ops to CLI/file operations [rec: old-dawn-8747].
- Node format: YAML frontmatter (`node_id` = uuid5 of the slug, `slug`, `title`, `created_at`, `parents` as slugs, optional `flywheel:` mapping) over a body that is the node content byte-for-byte — so `check`/`render`/`viz` parse it unchanged [rec: old-dawn-8747].
- Integration surface is one file format and `export`: the checker, renderer and visualizer were not modified, because they only ever read the two JSON exports [rec: old-dawn-8747].
- Flywheel is now optional rather than load-bearing, and the two compose: `backend: local` + `mirror: flywheel` keeps files canonical and Flywheel a regenerable projection, refreshed by `push --plan` → skill executes → `push --record-result`; first live push applied 7 ops with no revision conflicts [rec: old-dawn-8747] [rec: kind-valley-8040].
- The projection-trust gap is closed: `push --verify --against <fresh export>` detects drift the plan cannot see (missing nodes, body-hash and summary mismatches, revision skew), and a mirror-only slug legend node — regenerated on every push, excluded from import and verify — makes local slugs readable on the mirror; the first live verify caught and fixed three real byte deviations on this repo's own mirror [rec: careful-harbor-3902].
- The sequencing bet in patient-limit-9007 — build-vs-defer decided only after field dogfooding — was overtaken: the adapter shipped first, so the interface was proven by a second implementation rather than by field use [rec: patient-limit-9007] [rec: old-dawn-8747].
- **The mirror is currently UNREACHABLE and could not be refreshed** (2026-08-09). A 17-op plan failed on every op; nothing was written, the account is back to exactly its 458 starting nodes, and `push --record-result` was never run — so no `flywheel:` frontmatter changed and the local graph is untouched. `get_node` on the mirror state root (`cool-king-8586`) returns 404, `resolve_node_slug` returns `not_found`, and 0 of the 458 visible nodes belong to this project: the mirror is not on the account the current `FLYWHEEL_API_KEY` belongs to. Nothing is lost — local files are canonical and the mirror is a regenerable projection, so `push --plan` rebuilds it once the right account is identified. Needs the Operator [rec: sweet-aspen-3667].

## Negative knowledge

- [scope: mirroring a local graph to Flywheel | confidence: high | evidence: old-dawn-8747, kind-valley-8040] Flywheel mints its own slug on create, so nodes authored locally after the switch live there under a different slug while the markdown still cites the local one — `check` against a Flywheel export reported 25 dangling-pointer violations (I4/I5/I7) on a graph that checks 0/0 from the node files. The mirror is a readable projection, never the thing you check; slugs cross the boundary only through each file's `flywheel:` block.
- [scope: deferring slug translation on push | confidence: medium | evidence: kind-valley-8040] translation would make the mirror non-identical to source, breaking the byte-identical `content_sha256` change detector and forcing two-way translation on every update; the cost of *not* translating is now measured (above) rather than assumed.
- [scope: reading command output over ssh in this codebase | confidence: high | evidence: northern-tree-5868] `BoxController.ssh_exec` returns stdout followed by stderr, so an ssh host-key banner lands AFTER the payload, not before. Prefix-stripping a base64 blob therefore leaves trailing junk and fails with 'Incorrect padding'. Sentinel-frame both ends of any binary or structured payload.
- [scope: executing mirror pushes by hand instead of from plan bytes | confidence: high | evidence: careful-harbor-3902] `push --plan` cannot detect manual-push byte deviations — frontmatter shas are stamped from local bytes, so a hand-transcribed mirror write that drifts (lost newline, dropped blank line) looks clean to the planner; only `push --verify` against a fresh export catches it. Always push content extracted verbatim from the plan JSON.

## Provenance


- patient-limit-9007 — Operator directive opening this gap, with constraints and sequencing
- old-dawn-8747 — the adapter, the CLI subcommands, and this repo's migration onto it
- kind-valley-8040 — first live mirror push; measured mirror-consistency limits
- careful-harbor-3902 — verify + legend close the projection-trust gap; manual-push drift lesson
- northern-tree-5868 — ssh stream-ordering lesson from the benchmark's harvest path
- sweet-aspen-3667 — mirror unreachable from the rotated key; no partial writes; local graph canonical
