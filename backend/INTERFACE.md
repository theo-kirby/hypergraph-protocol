# Backend Interface

The Hypergraph skills are written against these abstract operations, not against any
concrete graph store. v0.0.1 ships one adapter
([flywheel-adapter.md](flywheel-adapter.md)); a future git-native backend should be a
drop-in second adapter implementing the same table.

Requirements on the backend: a DAG of nodes with markdown content, immutable node IDs,
immutable human-readable slugs, optimistic-locking writes, and JSON export of a
subgraph. Artifacts and tags are optional.

## Operations

| # | Operation | Signature (conceptual) | Used by | Notes |
|---|-----------|------------------------|---------|-------|
| 1 | `create_root` | `(title, content) → node` | init | Creates a parentless node. Called twice per project (record root, state root). |
| 2 | `append_record_node` | `(parent_ids, title, content, summary, repo_ctx) → node` | record, init, reconcile | Append-only; the returned slug is the node's permanent handle. Must support multiple parents. |
| 3 | `read_node` | `(node_id \| slug) → node` | all | Full body: title, content, summary, revision. |
| 4 | `list_children` | `(node_id) → [node-ref]` | orient, reconcile | Direct children, paged. |
| 5 | `get_tree` | `(node_id, depth) → topology` | orient | Bounded tree/DAG projection for cheap orientation. |
| 6 | `resolve_slug` | `(slug) → node_id` | all | Must surface ambiguity explicitly rather than guessing. |
| 7 | `update_state_node` | `(node_id, content, base_revision) → node` | **reconcile only** (I3) | Full-content replace with optimistic locking; conflicts surfaced, not silently merged. |
| 8 | `export_graph` | `(root_id) → JSON` | reconcile | Root + all descendants, with per-node `node_id`, `slug_name`, `title`, `content`, `parent_ids`, `created_at`. Feeds `tools/hypergraph.py`. |
| 9 | `attach_artifact` *(optional)* | `(node_id, files) → artifact-refs` | record | Evidence on record nodes only. |
| 10 | `tag` *(optional)* | `(node_id, tags)` | future | Reserved for `unreconciled` auto-tagging and `current-best`. |

## Contract notes

- **Slugs are the cross-graph pointer currency.** They must be immutable and
  resolvable for the life of the project. Anything the protocol writes into markdown
  (`## Provenance`, `[rec: …]`, `## State Impact` targets, the HWM) is a slug.
- **Two roots, two disjoint DAGs.** No backend edge may ever connect the record graph
  to the state graph (SPEC: pointers are markdown, not edges).
- **Append vs update.** Record graph uses only ops 1–2 for writes; state graph uses
  ops 1–2 at init (seeding) and op 7 thereafter. An adapter must make op 7's
  concurrency story explicit (lease, lock, CAS) — reconcile is single-writer by
  protocol, but the backend should still refuse a stale write.
- **Export determinism.** Op 8 output for the same graph revision should be stable
  enough for diffing; ordering by `created_at` then `node_id` is recommended.
