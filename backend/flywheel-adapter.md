# Flywheel Adapter

Maps [INTERFACE.md](INTERFACE.md) operations to Flywheel MCP tool calls. Canonical
tool semantics live in the Flywheel contract (`flywheel_get_contract`,
`flywheel_get_contract_section("graph")`, `…("stage_commit")`); this file is the
recipe book the skills follow.

Flywheel facts the protocol relies on:

- Node body = `title` + markdown `content` + optional `summary`. No typed fields.
- Every node gets an immutable `slug_name` (`adjective-noun-####`) on create.
- `commit_new_node` / `commit_node` are the only canonical persistence boundaries.
- Mutating writes are optimistic-locking (`expected_revision` /
  `base_committed_revision`), conflict = HTTP 409. MCP transport auto-manages
  idempotency keys, so retrying the same call after a wait is safe.

## Operation mapping

### 1. `create_root` → `flywheel_commit_new_node`

```jsonc
{
  "local_temp_node_id": "local-root-1",        // caller-local, must NOT be a real node_id
  "parent_ids": [],
  "staged_payload": {
    "title": "<project> — record",             // or "<project> — state"
    "content": "…",
    "summary": "",
    "repo_context": {                          // ALL keys required; null when not applicable
      "repo_url": null, "branch_name": null, "head_commit_sha": null,
      "origin_host": null, "updated_by": null, "external_transcript_ref": null
    }
  }
}
```

Save the returned `node_id` + `slug_name` into `.hypergraph/config.yml`.

### 2. `append_record_node` → `flywheel_commit_new_node` (or `flywheel_branch_node`)

Preferred: `flywheel_commit_new_node` with `parent_ids: [<causal parent(s)>]` and the
full staged payload (record-node template content, real `repo_context` when code is
involved: `repo_url`, `branch_name`, `head_commit_sha`).

`flywheel_branch_node` also works (creates a canonical child immediately, then edit
via lease + `commit_node`), but it needs the parent's `expected_revision` and a 409
retry loop — more calls for no benefit here. Use it only when you want the node to
exist before its content is ready.

Multiple causal parents: create with the primary parent, then `flywheel_add_parent`
for the rest.

### 3. `read_node` → `flywheel_get_node`

Relationship arrays on the response are not guaranteed complete — use op 4/5 tools for
traversal, not `get_node`.

### 4. `list_children` → `flywheel_get_node_children`

Page with `first` / `after`; `projection: "core"` is enough for orientation.

### 5. `get_tree` → `flywheel_get_node_tree`

Bounded root-aware tree/DAG projection from an anchor node. Orient uses this on the
state root: one call typically returns the whole state graph topology.

### 6. `resolve_slug` → `flywheel_resolve_node_slug`

Branch on `status`: `unique` / `context_resolved` → use the node_id;
`ambiguous` → stop and surface the candidates (never guess before mutating);
`not_found` → for the checker this is a dangling-pointer violation, for skills an error.

### 7. `update_state_node` → get → lease → commit

The full safe-update sequence (reconcile only — SPEC I3):

1. `flywheel_get_node` — read latest body + `committed_revision`.
2. `flywheel_acquire_stage_lease` on the node — yields `stage_session_id`.
3. Compose the new full content locally (state-node template).
4. `flywheel_commit_node` with:
   ```jsonc
   {
     "node_id": "…",
     "stage_session_id": "…",
     "base_committed_revision": <revision from step 1>,
     "staged_payload": { "title": "…", "content": "…", "summary": "…",
                          "repo_context": { /* all six keys, null ok */ } }
   }
   ```
   The payload is a **full replace** — include everything, not a diff.
5. `flywheel_release_stage_lease` (lease is session-scoped; release promptly).

On **409** `stale committed revision`: someone else committed since step 1. Re-read,
re-fold your delta on top of the new content, re-commit with the new revision. (Under
I3 this should not happen — treat it as a signal that a second writer is violating the
protocol, and say so.) On **409** `stage lease missing or expired`: re-acquire and
retry; heartbeat (`flywheel_heartbeat_stage_lease`) during long compositions.

### 8. `export_graph` → `flywheel_export_subgraph`

```jsonc
{ "node_ids": ["<root node_id>"], "include_descendants": true, "max_nodes": <bound> }
```

Run once per graph (record root, state root) and save to
`.hypergraph/cache/record.json` / `.hypergraph/cache/state.json` for
`tools/hypergraph.py`. The checker accepts the export as-is; note the export encodes
edges as `incoming_ids` (parents) / `outgoing_ids` (children), which the checker
normalizes along with `node_id` / `slug_name` / `title` / `content` / `created_at`. If the graph is larger than `max_nodes`, raise the bound — a truncated
export silently weakens every cross-graph check.

### 9. `attach_artifact` → prepare / upload / finalize

1. `flywheel_prepare_artifact_uploads` on the record node → batch token + signed URLs.
2. Upload **raw file bytes** to each signed URL (no JSON wrappers).
3. `flywheel_finalize_artifact_uploads` → appends all staged artifacts in one revision
   bump. Give every artifact a real `title` — it's the display label.

### 10. `tag` → `flywheel_create_node_tag` / `flywheel_set_node_tag_assignments`

Reserved for future work (`unreconciled` auto-tagging via hooks, one-only
`current-best`). Note `set_node_tag_assignments` takes `tag_ids` as a JSON array and
*omitting it clears all assignments* — always pass the full desired array.

## Write limits and failure handling

- **120 node creates/min, 2,000 creates/24h, 120 graph writes/min** (graph writes
  include existing-node commits, edge changes, deletes, tags, artifact finalization).
  Hypergraph's steady-state usage is far below this; bulk retro-recording should still
  pace itself.
- On **429**: honor `Retry-After`, then retry the same idempotent call.
- On **409**: never blind-retry — re-read, reconcile explicitly (recipes above).
- Cleanup during experimentation: `flywheel_bulk_delete_nodes` removes subtrees;
  remember slugs of deleted nodes stop resolving, which the checker will then flag in
  any provenance that cited them. Prefer never deleting reconciled record nodes.
