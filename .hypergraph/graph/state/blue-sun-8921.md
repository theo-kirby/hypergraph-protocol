---
node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
slug: blue-sun-8921
title: Storage interface
created_at: '2026-08-06T21:41:11.400955+00:00'
parents:
- cool-king-8586
summary: INTERFACE.md as a portability contract with one shipped implementation (node files); mirroring split into backend/mirror.md and the host contract demoted to backend/flywheel.md; working.
flywheel:
  node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
  slug: blue-sun-8921
  revision: 6
  pushed_at: '2026-08-09T11:42:29+00:00'
  content_sha256: 0dcc1bef7df423b6b9d199dd11f29f9c5ce7a2fea94f088fbbce4ef167a9370a
---
Status: working

## Current

- backend/INTERFACE.md defines the 10 abstract operations the protocol is written against (create_root, append_record_node, read_node, list_children, get_tree, resolve_slug, update_state_node, export_graph, attach_artifact, tag) [rec: crimson-dawn-7137].
- **It is now a portability contract rather than a menu.** One implementation ships — `backend/local-adapter.md`, node files in the repo — and the table states what a *replacement* store would have to satisfy. There is no `backend:` selector to set; storage is not a decision a project makes at init [rec: silver-ember-3035]. Two adapters existing at once was what previously proved the table swappable [rec: old-dawn-8747]; the claim now rests on the table's shape rather than on shipping a second one.
- Op 7's concurrency story is a body-hash compare-and-swap (`--expect`) with git as the merge substrate, and `--reconcile` is the mechanical I3 gate — the only commands that write state nodes refuse without it [rec: old-dawn-8747] [rec: silver-ember-3035].
- **`backend/local-adapter.md` lost its mirroring section** (105 lines) to a 5-line stub, and `## Bootstrapping from Flywheel` became `## Importing an existing graph`. Leaving mirror mechanics in the one file every skill symlinked into `references/` is exactly how the mirror stayed visible to agents that had no business knowing about it [rec: silver-ember-3035].
- **`backend/mirror.md` is new and symlinked nowhere.** It absorbs the mechanics, rewritten from "the skill executes" to "the CLI executes", and carries what had only ever been prose: the measured slug-divergence consequences, the legend/lineage/verify rules, why results are folded incrementally, and `## Re-homing a hosted graph into the repo` — the migration path previously buried in init step 8, which is the answer for pre-0.0.2 hosted projects [rec: silver-ember-3035].
- **`backend/flywheel-adapter.md` → `backend/flywheel.md`**, ~70 lines, banner-marked *"not an agent-facing document"*. Demoted rather than deleted: it is the only record of the six required `repo_context` keys, `local_temp_node_id`, `base_committed_revision` semantics, the 409/429 contract, the write limits, and add-parent-before-remove ordering — all of which the executing `push` depends on [rec: calm-sand-3399]. The rename and the five skills' symlink deletions were one commit, so no revision in history has dangling references.
- Constraint: no operation may create edges between the two roots — cross-graph pointers stay markdown [rec: spring-pine-7256].
- Node-file frontmatter carries two identity blocks that are never confused: `origin:` — where an imported node came from (immutable, written once by `import --fork`, read by nothing) — and `flywheel:` — this project's own mirror identity. Before the split one field was doing three jobs at once: provenance, push target, and change-detection baseline [rec: copper-moss-3669] [rec: tender-moss-3792]. The two are no longer described as peers: `origin:` is protocol, the mirror block is bookkeeping [rec: silver-ember-3035].
- The mirror projects the repo, never the archive. `local-adapter.md` separates the two `import` cases explicitly — re-homing a graph you own (no `--fork`; the source stays the push target) from adopting somebody else's (`--fork` mandatory) — because getting it wrong is silent in both directions: the first omits the whole legacy history from every push, the second duplicates the entire graph [rec: tender-moss-3792].
- Re-parenting an existing mirror node (`nodes:add-parent` / `nodes:remove-parent`): add first, then remove, so the child is never momentarily parentless; all four optimistic-lock revisions are required and the add bumps the child's revision, so re-read between calls. Verified live on two a3go nodes [rec: tender-moss-3792] [rec: northern-willow-0469].
- `nodes:commit-new` also requires `local_temp_node_id`; omitting it is a server-side 422, so nothing is created. Identity can come back nested under `node: {node_id, slug_name, revision}` [rec: northern-willow-0469].
- **Op 10 (tags) is implemented; op 9 (artifacts) is not** [rec: clear-moss-4527]. A tag is a `tags:` list of *names* in node frontmatter, with the vocabulary — colours, `one_only`/`track_history`, and whatever id a backend minted — in a committed `.hypergraph/tags.yml` keyed by graph kind, because declaration is per graph root and there are two. **Names are the portable identity**, for the same reason `parents:` holds slugs: every store mints its own tag ids, so an id is as local to a store as a mirror's slug is. `synth_tag` derives a colour pair from `sha256(name)`, which is what keeps `tags.yml` optional — an undeclared name still works, and two machines agree on its colour without coordinating.
- **A tag is annotation, and no invariant reads one.** INTERFACE says so as a contract note rather than leaving it to be discovered: a claim that exists only as a tag is invisible to the protocol, so the home for a claim is a node body. `check` is tag-blind with exactly one exception — where `tags.yml` exists, an undeclared name is a *warning*, never a violation [rec: clear-moss-4527].
- **Assignment is an atomic replace, and that property is load-bearing.** A re-issued assignment cannot duplicate anything, so a 409 on one may be re-read and re-issued in place — the only operation here where that is safe. A *declaration* has no such property (deleting a tag definition un-tags every node that used it), so an implementation must resolve an existing name before declaring, always [rec: clear-moss-4527].

## Negative knowledge

- [scope: mode-A adoption mirrors | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] a mirror can verify clean while holding almost none of the graph. `import` stamped every node with the archive's `flywheel:` identity, so `push_plan` omitted all of them as already-pushed — they were on Flywheel, just on somebody else's graph — and `push --verify` was run against an export that spliced the archive roots in, which made those orphaned ids resolve. Measured on a3go: 3 record nodes mirrored of 111, with `push --plan` reporting 0 creates and verify exiting 0. **Now mechanically unreachable**: `mirror_root_ids()` refuses to treat an `archive:` root as a mirror root [rec: silver-ember-3035].
- [scope: re-parenting nodes on a Flywheel mirror | confidence: high | evidence: northern-willow-0469] `add-parent`/`remove-parent` bump the committed revision on **both** ends of the edge, so `push --verify` reports revision skew against the node files afterwards until the mirror's revisions are fed back. Content is untouched; only the revision drifts.
- [scope: documenting a mechanism agents should not use | confidence: high | evidence: silver-ember-3035] a reference doc symlinked into a skill's `references/` is part of that skill's context whether or not the skill's own body mentions it. Deleting the backend-dispatch preambles alone would have left every MCP recipe, the lease dance and the rate budgets one hop away. Moving the prose out of the symlinked file — not merely stopping citing it — is what makes a mechanism actually absent.
- [scope: driving headless agent harnesses | confidence: high | evidence: scarlet-orchard-8774] an agent harness's **run log is not its session record**, and the difference is silent. pi's print mode writes only the final answer — 82 bytes for an entire run — while the turn-by-turn tree with tool calls, tokens and cost auto-saves to `~/.pi/agent/sessions/`. A harvest scoped to the workspace would have torn the box down with the evidence still on it and surfaced the loss only at analysis. Verify a measurement channel on a throwaway box before a run depends on it.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — markdown-pointers decision the interface encodes
- crimson-dawn-7137 — INTERFACE.md + the first adapter landed (M2)
- old-dawn-8747 — second adapter (local-adapter.md); per-adapter op-7 story
- kind-valley-8040 — adapter doc corrected from the first live mirror push
- copper-moss-3669 — fork-import decision: one field doing three jobs; the archive-spliced verify
- tender-moss-3792 — origin:/flywheel: split shipped; re-home vs adopt documented; re-parenting recipe
- northern-willow-0469 — re-parenting and commit-new payload shape proven live on a3go
- silver-ember-3035 — INTERFACE.md re-scoped as a portability contract; mirroring moved to backend/mirror.md
- calm-sand-3399 — flywheel-adapter.md renamed and demoted to CLI internals
- clear-moss-4527 — op 10 shipped: names as the portable identity, tags.yml, and the contract note that no invariant reads a tag
