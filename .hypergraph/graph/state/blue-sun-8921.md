---
node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
slug: blue-sun-8921
title: Backend adapter
created_at: '2026-08-06T21:41:11.400955+00:00'
parents:
- cool-king-8586
summary: 10 abstract ops + Flywheel MCP recipes; working.
flywheel:
  node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
  slug: blue-sun-8921
  revision: 1
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: a20425c77621a1d48b76dd815ff5ed1465a8989378b74a3e4c4289e3fc12d41d
---
Status: working

## Current

- backend/INTERFACE.md defines the 10 abstract operations the skills are written against (create_root, append_record_node, read_node, list_children, get_tree, resolve_slug, update_state_node, export_graph, attach_artifact, tag) [rec: crimson-dawn-7137].
- Two adapters now implement the table, so the interface is proven swappable rather than asserted: backend/flywheel-adapter.md (MCP) and backend/local-adapter.md (git-native node files) [rec: old-dawn-8747].
- backend/flywheel-adapter.md maps each op to Flywheel MCP recipes verified against the live contract: commit_new_node payload shape (six required repo_context keys), get → lease → commit_node → release for state updates, export_subgraph with include_descendants, 409/429 handling, write limits [rec: crimson-dawn-7137].
- Op 7's concurrency story is explicit per adapter, as the interface requires: Flywheel refuses a stale write by `base_committed_revision` (409); the local adapter by a body-hash compare-and-swap (`--expect`), with git as the merge substrate [rec: old-dawn-8747].
- `backend:` in `.hypergraph/config.yml` became the live dispatch key — every skill reads it and follows the matching adapter reference; it was declarative and read by nothing before [rec: old-dawn-8747].
- Constraint: no adapter op may create edges between the two roots — cross-graph pointers stay markdown [rec: spring-pine-7256].
- Optional ops stay unimplemented locally: artifacts (op 9) and tags (op 10), used by no skill [rec: old-dawn-8747].

## Negative knowledge

None yet.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — markdown-pointers decision the interface encodes
- crimson-dawn-7137 — INTERFACE.md + flywheel-adapter.md landed (M2)
- old-dawn-8747 — second adapter (local-adapter.md); per-adapter op-7 story; backend: becomes the dispatch key
