---
node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
slug: blue-sun-8921
title: Backend adapter
created_at: '2026-08-06T21:41:11.400955+00:00'
parents:
- cool-king-8586
summary: '10 abstract ops + Flywheel and local adapters; origin:/flywheel: identity split; re-parenting recipe; working.'
flywheel:
  node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
  slug: blue-sun-8921
  revision: 4
  pushed_at: '2026-08-08T11:35:36+00:00'
  content_sha256: 3d1432a797bb1d65e932e3e66b720e0db0c480eec1a40a99c7989239ab73fc95
---
Status: working

## Current

- backend/INTERFACE.md defines the 10 abstract operations the skills are written against (create_root, append_record_node, read_node, list_children, get_tree, resolve_slug, update_state_node, export_graph, attach_artifact, tag) [rec: crimson-dawn-7137].
- Two adapters now implement the table, so the interface is proven swappable rather than asserted: backend/flywheel-adapter.md (MCP) and backend/local-adapter.md (git-native node files) [rec: old-dawn-8747].
- backend/flywheel-adapter.md maps each op to Flywheel MCP recipes verified against the live contract: commit_new_node payload shape (six required repo_context keys), get → lease → commit_node → release for state updates, export_subgraph with include_descendants, 409/429 handling, write limits [rec: crimson-dawn-7137].
- Op 7's concurrency story is explicit per adapter, as the interface requires: Flywheel refuses a stale write by `base_committed_revision` (409); the local adapter by a body-hash compare-and-swap (`--expect`), with git as the merge substrate [rec: old-dawn-8747].
- `backend:` in `.hypergraph/config.yml` became the live dispatch key — every skill reads it and follows the matching adapter reference; it was declarative and read by nothing before [rec: old-dawn-8747].
- Constraint: no adapter op may create edges between the two roots — cross-graph pointers stay markdown [rec: spring-pine-7256].
- Mirror semantics documented precisely in local-adapter.md after the first live push: the projection is readable, not independently checkable, and a `create` whose parent is also a create in the same plan carries `null` in `parent_flywheel_ids` for the executor to substitute [rec: kind-valley-8040].
- Node-file frontmatter carries two identity blocks that are never confused: `origin:` — where an imported node came from (backend, node_id, slug, revision, exported_at; immutable, written once by `import --fork`, read by nothing) — and `flywheel:` — this project's own mirror identity, written only by `push --record-result`. Before the split one field was doing three jobs at once: provenance, push target, and change-detection baseline [rec: copper-moss-3669] [rec: tender-moss-3792].
- The mirror projects the repo, never the archive. local-adapter.md now separates the two `import` cases explicitly — re-homing a graph you own (no `--fork`; the source stays the push target) from adopting somebody else's (`--fork` mandatory) — because getting it wrong is silent in both directions: the first omits the whole legacy history from every push, the second duplicates the entire graph [rec: tender-moss-3792].
- Adapter §10a covers re-parenting an existing mirror node (`flywheel_add_parent` / `flywheel_remove_parent`; CLI `nodes:add-parent` / `nodes:remove-parent`): add first, then remove, so the child is never momentarily parentless; all four optimistic-lock revisions are required and the add bumps the child's revision, so re-read between calls. Verified live on two a3go nodes [rec: tender-moss-3792] [rec: northern-willow-0469].
- `flywheel_commit_new_node` / `nodes:commit-new` also requires `local_temp_node_id`; omitting it is a server-side 422, so nothing is created. Identity comes back nested under `node: {node_id, slug_name, revision}` [rec: northern-willow-0469].
- Optional ops stay unimplemented locally: artifacts (op 9) and tags (op 10), used by no skill [rec: old-dawn-8747].

## Negative knowledge

- [scope: mode-A adoption mirrors | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] a mirror can verify clean while holding almost none of the graph. `import` stamped every node with the archive's `flywheel:` identity, so `push_plan` omitted all of them as already-pushed — they were on Flywheel, just on somebody else's graph — and `push --verify` was run against an export that spliced the archive roots in, which made those orphaned ids resolve. Measured on a3go: 3 record nodes mirrored of 111, with `push --plan` reporting 0 creates and verify exiting 0.
- [scope: re-parenting nodes on a Flywheel mirror | confidence: high | evidence: northern-willow-0469] `add-parent`/`remove-parent` bump the committed revision on **both** ends of the edge, so `push --verify` reports revision skew against the node files afterwards until the mirror's revisions are fed back through `push --record-result`. Content is untouched; only the revision drifts.
- [scope: driving headless agent harnesses | confidence: high | evidence: scarlet-orchard-8774] an agent harness's **run log is not its session record**, and the difference is silent. pi's print mode writes only the final answer — 82 bytes for an entire run — while the turn-by-turn tree with tool calls, tokens and cost auto-saves to `~/.pi/agent/sessions/`. A harvest scoped to the workspace would have torn the box down with the evidence still on it and surfaced the loss only at analysis. Verify a measurement channel on a throwaway box before a run depends on it.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — markdown-pointers decision the interface encodes
- crimson-dawn-7137 — INTERFACE.md + flywheel-adapter.md landed (M2)
- old-dawn-8747 — second adapter (local-adapter.md); per-adapter op-7 story; backend: becomes the dispatch key
- kind-valley-8040 — adapter doc corrected from the first live mirror push
- copper-moss-3669 — fork-import decision: one field doing three jobs; the archive-spliced verify
- tender-moss-3792 — origin:/flywheel: split shipped; re-home vs adopt documented; adapter §10a re-parenting
- northern-willow-0469 — §10a and commit-new payload shape proven live on a3go
