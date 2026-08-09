# Storage Interface

The protocol is defined over these abstract operations rather than over any concrete
graph store. **One implementation ships** — [local-adapter.md](local-adapter.md),
git-native: markdown node files committed in the repo, driven by
`tools/hypergraph.py`, no network and no account.

So this table is not a menu. It is the **portability contract**: what a replacement
store would have to satisfy for the rest of SPEC.md to hold unchanged, and the reason
nothing in the protocol above the Storage section mentions files. There is no
`backend:` selector to set — storage is not a decision a project makes at init.

Requirements on a store: a DAG of nodes with markdown content, immutable node IDs,
immutable human-readable slugs, optimistic-locking writes, and JSON export of a
subgraph. Artifacts and tags are optional; the shipped implementation omits artifacts
and implements tags as frontmatter (op 10 below).

Mirroring committed node files to a hosted graph ([mirror.md](mirror.md)) is a separate
concern and does **not** go through this table: a mirror is a projection the CLI
writes, not a store the protocol reads.

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
| 10 | `tag` *(optional)* | `declare(root_id, name, style) → tag-ref`; `assign(node_id, [name]) → ()` | record, import, push, heal | Vocabulary is declared **per graph root**; assignment is an **atomic replace** of a node's whole set. **Names**, not ids, are the portable identity. |

## Contract notes

- **Slugs are the cross-graph pointer currency.** They must be immutable and
  resolvable for the life of the project. Anything the protocol writes into markdown
  (`## Provenance`, `[rec: …]`, `## State Impact` targets, the HWM) is a slug.
- **Two roots, two disjoint DAGs.** No backend edge may ever connect the record graph
  to the state graph (SPEC: pointers are markdown, not edges).
- **Append vs update.** Record graph uses only ops 1–2 for writes; state graph uses
  ops 1–2 at init (seeding) and op 7 thereafter. An implementation must make op 7's
  concurrency story explicit (lease, lock, CAS) — reconcile is single-writer by
  protocol, but the store should still refuse a stale write. The shipped one uses a
  body-hash CAS (`--expect`), with git as the merge substrate underneath.
- **Export determinism.** Op 8 output for the same graph revision should be stable
  enough for diffing; ordering by `created_at` then `node_id` is recommended.
- **A tag name is the portable identity (op 10).** Every store that implements tags
  mints its own ids, so an id is as local to a store as a mirror's slug is. The
  protocol therefore travels names — the same choice, for the same reason, as
  `parents:` holding slugs. A store's ids are recorded beside the name as
  bookkeeping and never read as identity.
- **Assignment is an atomic replace, and that is load-bearing.** Because a re-issued
  assignment cannot duplicate anything, a conflicting assignment may be re-read and
  re-issued in place — the one operation here for which that is safe. A `declare` has
  no such property: a second declaration of the same name is unrecoverable, because
  deleting a tag definition un-tags every node that used it. Implementations must
  resolve an existing name before declaring, always.
- **A tag is annotation, and nothing above the Storage section reads one.** No
  invariant, no checker rule, no renderer decision depends on a tag. A claim that
  exists only as a tag is invisible to the protocol — which is the point of saying so
  here rather than leaving it to be discovered: the right home for a claim is a node
  body, and a tag is a way to find nodes, not a way to assert things about them.
