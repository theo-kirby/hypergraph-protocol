# Flywheel: the host's payload contract

**Not an agent-facing document.** No skill reads this, and none should. It is the
payload/lease contract that `hypergraph push` codes against — kept because it is the
only written record of several things the live OpenAPI does not state: `repo_context`'s
six required keys, `local_temp_node_id`, `base_committed_revision` semantics, the
409/429 contract, the write limits, and add-parent-before-remove ordering.

For what mirroring *is* and why, read [mirror.md](mirror.md). For the protocol's
storage, read [local-adapter.md](local-adapter.md).

Facts the mirror code relies on:

- Node body = `title` + markdown `content` + optional `summary`. No typed fields.
- Every node gets an immutable `slug_name` (`adjective-noun-####`) on create — which
  is why a mirrored node's slug diverges from the local one (mirror.md).
- `commit_new_node` / `commit_node` are the only canonical persistence boundaries.
- Mutating writes are optimistic-locking (`expected_revision` /
  `base_committed_revision`); conflict = HTTP 409.
- **Every mutating endpoint's documented success schema is `{}`.** Probe the response
  and fail loudly; never default a missing `revision` to 0.

CLI equivalents of each call below: `flywheel help <command> --format=json` returns a
machine-readable schema for all of them.

## Calls the mirror makes

### Create a node → `nodes:commit-new`

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

`hypergraph mirror roots --mint` uses this, and appends the returned
`node_id` + `slug_name` to the config under `mirror_roots:`.

### Create with parents → `nodes:commit-new`

Same call, with `parent_ids: [<causal parent(s)>]` and the full staged payload —
record-node content, and a real `repo_context` when code is involved (`repo_url`,
`branch_name`, `head_commit_sha`, parsed out of the node's `## Repo` section).

`branch_node` also creates children but needs the parent's `expected_revision` and a
409 retry loop — more calls for no benefit, so `push` does not use it.

Multiple causal parents: create with the primary parent, then add the rest (below).

### Update a node → get → lease → commit → release

The full safe-update sequence. `FlywheelCliTransport.commit()` implements it with
the release in a `finally`, so 409 semantics live in exactly one place:

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

### Export a subgraph → `export:subgraph`

```jsonc
{ "node_ids": ["<root node_id>"], "include_descendants": true, "max_nodes": <bound> }
```

This is what `push --verify` diffs against and what `mirror pull` splits. The export
encodes edges as `incoming_ids` (parents) / `outgoing_ids` (children), which
`load_graph` normalizes along with `node_id` / `slug_name` / `title` / `content` /
`created_at` — so the same reader handles it and a local export.

`max_nodes` defaults to 500 and tops out at 5000. **A truncated export is a hard
error, not a smaller answer**: every node past the cut reads as drift in `verify` and
silently weakens every cross-graph check. Do not run `check` against one of these at
all — a mirror export reports dangling pointers for every locally-minted slug
(mirror.md).

### Tags → `tags:create` / `tags:assign`

Op 10, and the host has implemented it all along. There is **no `tags:list`** — read
the vocabulary out of any node's full projection.

```bash
# 1. read: the vocabulary lives on the graph root, under `graph_tags`
flywheel nodes:get --node_id <root> --projection full     # → {…, "graph_tags": [ … ]}

# 2. declare: locks against the ROOT revision, which every create bumps
flywheel tags:create --root_node_id <root> --name "kind:experiment" \
    --expected_revision 12 --bg_color "#1F3A5F" --text_color "#E8F0FB"
#   optional store-true flags: --one_only --track_history

# 3. assign: atomic replace of the node's whole set, locks against the NODE revision
flywheel tags:assign --node_id <node> --tag_ids t1,t2 --expected_revision 22
flywheel tags:assign --node_id <node> --tag_ids "" --expected_revision 22   # clear
```

| op | endpoint | lock |
| --- | --- | --- |
| `tags:create` | `POST /nodes/{root_node_id}/tags` | root revision |
| `tags:assign` | `PUT /nodes/{node_id}/tags` | node revision |
| `tags:update` | `PATCH /nodes/{root_node_id}/tags/{tag_id}` | root revision |
| `tags:delete` | `DELETE /nodes/{root_node_id}/tags/{tag_id}` | root revision |

Five traps, all of them cheap to hit:

- **`tags:create` does not return the tag.** Measured against the live host: it returns
  the updated *graph root node* — `content`, `artifacts`, `graph_projection`,
  `can_write` — with no `tag_id` anywhere in it. The tag really is created; the
  response simply is not it. So the new tag's id must come from **re-reading the root
  and resolving by name**, which is the same read that gets you the bumped root
  revision, and the same lookup that makes a crashed run find its tag instead of
  creating a second one. Anything that trusts this response for identity fails on the
  very first tag.

- **An absent `graph_tags` key is not "no tags".** Reading it that way makes the next
  push re-create the entire vocabulary, and a duplicate definition cannot be cleanly
  merged. Raise instead.
- **A node's own `graph_tags` copy is not authoritative.** In a real 189-node graph
  only 130 nodes echoed it while the other 59 carried populated `tag_ids` beside an
  empty list. Union across every node and let the parentless node win.
- **`--tag_ids` is comma-joined**, so a comma inside a tag name is unshippable.
  Validate names before they reach the wire.
- **`--one_only` and `--track_history` are store-true flags**, not `--k=v`. A helper
  that renders `--{k}={v}` for anything non-`None` turns a Python `False` into the
  *truthy string* `--one_only=False`. Omit them when false; pass them bare when true.

Every mutating response here is `{}` on success, so the created tag's id and the
node's new revision are both read back rather than assumed.

### Re-parenting → `nodes:add-parent` / `nodes:remove-parent`

Not an INTERFACE operation — a mirror-repair move. It exists for one situation: an
adopted project mirrors a node under a placeholder parent (typically the mirror root)
before its real parent is on the mirror, and the true edge has to be restored once the
parent lands. **Add first, then remove**, so the node is never momentarily parentless:

```bash
flywheel nodes:add-parent    --node_id <child> --parent_id <true parent> \
    --expected_revision <child rev> --expected_parent_revision <parent rev>
flywheel nodes:remove-parent --node_id <child> --parent_id <placeholder parent> \
    --expected_revision <child rev, now bumped> --expected_parent_revision <its rev>
```

MCP equivalents: `flywheel_add_parent` / `flywheel_remove_parent` (full-surface only;
HTTP `POST /nodes/{node_id}/parents/{add,remove}`). All four revisions are required
optimistic locks — read them with `flywheel_get_node` immediately before each call, and
re-read after the add, because it bumps the child's revision. Both are **graph writes**,
so they count against the 120/min graph-write budget. On 409, re-read and retry; the
add validates against cycles and refuses an edge that would create one.

Prove it on a single node before trusting it on a batch. If a node cannot be
re-parented, leave the placeholder edge in place and record the limitation — never
re-mint the mirror to fix topology.

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
