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
- backend/flywheel-adapter.md maps each op to Flywheel MCP recipes verified against the live contract: commit_new_node payload shape (six required repo_context keys), get → lease → commit_node → release for state updates, export_subgraph with include_descendants, 409/429 handling, write limits [rec: crimson-dawn-7137].
- Constraint: no adapter op may create edges between the two roots — cross-graph pointers stay markdown [rec: spring-pine-7256].

## Negative knowledge

None yet.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — markdown-pointers decision the interface encodes
- crimson-dawn-7137 — INTERFACE.md + flywheel-adapter.md landed (M2)