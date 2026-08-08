# Local (git-native) Adapter

Maps [INTERFACE.md](INTERFACE.md) operations to files in the repo and subcommands of
`tools/hypergraph.py`. No network, no MCP, no account: the graphs live in the working
tree and travel with the repo.

Facts the protocol relies on:

- **Node = one markdown file**: `.hypergraph/graph/<record|state>/<slug>.md`, committed.
  YAML frontmatter carries identity and edges; everything below the closing `---` is the
  node `content` byte-for-byte — the exact string the checker parses.
- **Slug = filename = frontmatter `slug`**, `adjective-noun-####` (`SLUG_RE`), minted on
  create and never rewritten. Slugs are the cross-graph pointer currency.
- **`node_id = uuid5(HYPERGRAPH_NS, slug)`** — deterministic, so ids are reproducible
  from the files alone and never depend on randomness or on a server.
- **`parents` holds slugs, not ids** — readable and diffable; `export` resolves them.
- **Git is the concurrency substrate.** Op 7 additionally carries a content-hash CAS
  (`--expect`) so a stale in-tree write is refused rather than silently applied.

```markdown
---
node_id: 3e64ea0a-f035-5204-8cf2-465735478d01
slug: bright-harbor-2001
title: local — state
created_at: '2026-08-02T00:00:00+00:00'
parents: []
summary: ''
origin:                         # only on nodes from `import --fork` (see §Bootstrapping)
  backend: flywheel             # immutable provenance; never a push target
  node_id: 8e1c…                # the archive's id
  slug: bright-harbor-2001      # the archive's slug — same as `slug:` above
  revision: 3
  exported_at: '2026-08-01T00:00:00+00:00'
flywheel:                       # only present once mirrored (see §Mirroring)
  node_id: 9e68…
  slug: wild-river-2201
  revision: 3
  pushed_at: '2026-08-02T04:00:00+00:00'
  content_sha256: ab12…         # what was last pushed — the change detector
---
Status: working

## Current
…
```

Working fixture: [`tools/fixtures/local-graph/`](../tools/fixtures/local-graph/) — five
node files plus the JSON they export to.

## Operation mapping

### 1. `create_root` → `hypergraph new <kind> --root`

```bash
hypergraph new record --root --title "<project> — record" --body record-root.md
hypergraph new state  --root --title "<project> — state"  --body overview.md \
                      --reconcile [--hwm none]
```

The state root's `## Reconciliation` block (`high_water_mark`, `reconciled_at`) is
generated for you (SPEC I5). Each command prints the minted slug as its first stdout
field — capture it (`SLUG=$(hypergraph new … | awk '{print $1}')`) and write both roots'
`node_id` + `slug` into `.hypergraph/config.yml`. A second root per graph is refused.

### 2. `append_record_node` → `hypergraph new record`

```bash
hypergraph new record --title "…" --body body.md \
    --parent <causal-slug> [--parent <second-causal-slug>] \
    --impact "<state-slug> — <delta>" [--impact "NEW <kebab-name> — <delta>"] \
    --repo-auto
```

`--body` carries the prose sections (`## What / ## Why / ## Method / ## Result`) and
accepts `-` for stdin. The CLI **generates** `## Repo` (from local `git` reads when
`--repo-auto`) and `## State Impact` (from the flags), so the machine-parsed sections
are well-formed by construction. Use `--none "<reason>"` instead of `--impact` when
current state truly doesn't change. Multiple `--parent` flags = multiple causal parents.

Before writing, the command runs the real checker over the candidate node: an impact
target that resolves to no state node, an unparseable impact line, or a missing
`## State Impact` fails at authoring time (exit 2, nothing written) rather than at
`check` time.

### 3. `read_node` → read the file

`.hypergraph/graph/<kind>/<slug>.md`. Frontmatter above the second `---`, content below.
For op 7 you also want the body hash: `hypergraph update <slug> --print-sha`.

### 4. `list_children` → grep the `parents` frontmatter

```bash
grep -l "^- <slug>$" .hypergraph/graph/state/*.md      # block-style parents list
```

Or, structurally, read the exported JSON — for the state graph that is one small file.

### 5. `get_tree` → `STATE.md`

`hypergraph render` already emits the state graph as an indented tree, frontier first.
Orientation under this backend is two file reads (`.hypergraph/config.yml`, `STATE.md`),
not a traversal.

### 6. `resolve_slug` → the path *is* the resolution

`.hypergraph/graph/<kind>/<slug>.md` exists or it doesn't; filenames are unique per
graph, so ambiguity is structurally impossible. `load_local_nodes` errors if a filename
and its frontmatter `slug` disagree.

### 7. `update_state_node` → `hypergraph update` (read → compare-and-swap)

Reconcile only (SPEC I3). The full safe sequence:

```bash
SHA=$(hypergraph update <slug> --print-sha)      # 1. read the current body hash
# 2. compose the complete new content locally (state-node template) → new.md
hypergraph update <slug> --body new.md --expect "$SHA" --reconcile
```

- `--expect` is the optimistic lock: if the body changed since you read it, the write is
  refused (exit 2) with both hashes, and the file is left untouched. Re-read, re-fold
  your delta onto the current content, retry. This is INTERFACE's "the backend should
  still refuse a stale write".
- `--reconcile` is the I3 gate: without it the command refuses to touch any state node
  and points at the reconcile skill.
- Record nodes are refused outright — the record graph is append-only; corrections are
  new child nodes.
- `--body` is a **full replace**, like the Flywheel adapter's payload. Compose the whole
  node, not a diff. The new content is checker-validated before the write lands.

### 8. `export_graph` → `hypergraph export`

```bash
hypergraph export --config .hypergraph/config.yml       # → .hypergraph/cache/{record,state}.json
```

Emits the canonical export shape (`node_id`, `slug_name`, `title`, `content`, `summary`,
`parent_ids`, `created_at`), nodes ordered by `created_at` then `node_id` per
INTERFACE's determinism note. This is the *whole* integration surface: `check`,
`render`, and `viz` consume these files without knowing which backend produced them.
The cache stays gitignored — it is regenerable from the node files at any time.

### 9. `attach_artifact` *(optional)* — not implemented

Commit evidence into the repo and reference it by path from `## Method` / `## Result`.

### 10. `tag` *(optional)* — not implemented

`check` already enumerates unreconciled nodes from the high-water mark.

## Bootstrapping from Flywheel

`import` explodes graph-export JSON into node files, preserving the source `node_id` and
`slug_name` **verbatim** — so an existing project's config, provenance slugs, and HWM
all stay valid across the migration:

```bash
# fetch with flywheel_export_subgraph (include_descendants: true) → cache files, then:
hypergraph import --record .hypergraph/cache/record.json \
                  --state  .hypergraph/cache/state.json
git add .hypergraph/graph && git commit -m "Import the graph into the repo"
```

`import` is idempotent (unchanged files are skipped) and refuses to clobber a differing
file without `--force`. It stamps each node's `flywheel:` block so the mirror knows what
has already been pushed — this is the **re-home** case: you own the source graph and
you keep mirroring to it, so its ids stay the push target. Do not pass `--fork` here.

**Adopting a project with a pre-protocol past** (the hypergraph-adopt skill, mode A):
`import --fork`. The graph you are importing belongs to somebody else, so the copy
takes its own mirror identity:

- node_ids and slugs are preserved verbatim, as always — config, provenance slugs and
  the HWM stay valid;
- the source ids are written to **`origin:`** (`backend`, `node_id`, `slug`,
  `revision`, `exported_at`) — immutable provenance, read by nothing;
- **`flywheel:` is omitted**, so `push --plan` plans every imported node as a `create`
  under roots this project owns. The project re-publishes its whole imported history
  with the original topology (SPEC: Adoption epochs).

Getting this wrong is silent in both directions: import a foreign graph *without*
`--fork` and the mirror push omits every legacy node (nothing is created, `--verify`
still passes if the archive is spliced into the export); import your own graph *with*
`--fork` and the next push duplicates the entire graph.

The source graph stays untouched as the frozen archive (`archive:` in config). Artifacts
do **not** survive import — the local backend has no artifact op (§9) — so the archive
reference is the only pointer to them, and `push --lineage` says so at the mirror record
root (below). In epoch-split mode (huge graphs, history left on the archive) the marker
is authored with `--root`: node files can only parent on slugs that resolve locally, so
the archive lineage is recorded in the marker's content instead of as a parent edge.

## Mirroring to Flywheel

Local files stay canonical; Flywheel becomes a regenerable, continuously-updated
projection. **The mirror projects the repo, never the archive** — for an adopted
project the mirror carries the full imported history under this project's own roots,
not a pointer to the graph it forked from. `tools/hypergraph.py` never makes an MCP
call, so the push is two steps with the skill layer in between:

```bash
hypergraph push --plan -o /tmp/plan.json      # 1. diff local files vs `flywheel:` frontmatter
# 2. the skill executes plan.ops in order via flywheel-adapter.md §1/§2/§7
hypergraph push --record-result /tmp/results.json   # 3. fold returned ids back in
```

The plan is ordered — creates come parents-first (topological, ties broken by
`created_at`). A `create` whose parent is *also* a create in the same plan carries
`null` in `parent_flywheel_ids`; because the ordering guarantees the parent was already
committed, the executor substitutes the id it just received:

```jsonc
{"op": "create", "graph": "record", "slug": "calm-fern-1003",
 "title": "…", "content": "…", "summary": "",
 "parent_slugs": ["brave-otter-1002"], "parent_flywheel_ids": ["9e68…"],
 "created_at": "…", "content_sha256": "…"}

{"op": "update", "graph": "state", "slug": "quiet-summit-2002",
 "flywheel_node_id": "9e68…", "base_revision": 3, "content": "…", "content_sha256": "…"}
```

- `create` → `flywheel_commit_new_node` (adapter §1/§2) with `parent_ids:
  parent_flywheel_ids`.
- `update` → lease → `flywheel_commit_node` with `base_committed_revision:
  base_revision` → release (adapter §7). `base_revision` is `null` for graphs bootstrapped
  by `import` (the export carries no revision) — read it with `flywheel_get_node` first.
- Nodes whose body hash already matches `flywheel.content_sha256` are omitted entirely,
  so a re-push after no changes is a no-op.
- A **record** node whose body changed after being pushed lands in `plan.violations` and
  `push --plan` exits 1 — the record graph is append-only, and that edit must not be
  mirrored. Fix the local edit rather than applying the plan.

Results feed back as a list of `{slug, flywheel: {node_id, slug_name, revision},
content_sha256}` (top level or under `"results"`); `push --record-result` writes them
into each file's `flywheel:` block. **Record results incrementally** on a large plan —
in batches of roughly 20, not once at the end. `push --plan` is a diff, so a run that
dies midway resumes safely *only* for the batches already recorded; anything created
but unrecorded is created a second time on the retry, and duplicate mirror nodes cannot
be cleanly merged. Above `PUSH_CREATE_WARN` (200) creates, `push --plan` prints this
warning to stderr itself and names epoch-split as the way to mirror less history.

**The mirror is a readable projection, not an independently valid graph.** Content is
pushed byte-identical, but Flywheel mints its own `slug_name` on create — so a node
authored locally as `old-dawn-8747` may live there as `purple-dawn-2034`, while every
`## Provenance` line, `[rec: …]` citation, impact target and the HWM still say
`old-dawn-8747`. Consequences, measured on this repo's first mirrored reconcile:

- Running `check` against a **Flywheel export** reports I4/I5/I7 dangling-pointer
  violations for every locally-minted slug (25 of them here), even though the same graph
  checks clean from the node files. Check the source, never the projection.
- Slugs resolve across the boundary only through each file's `flywheel:` block; inside
  Flywheel's UI they do not resolve natively.
- Nodes that predate the migration are unaffected — `import` preserved their slugs, so
  only nodes *created* after the switch to `local` diverge.

Slug translation on push would fix this and is deliberately deferred: it makes the
mirror non-identical to source, so every update would have to translate in both
directions and the byte-identical change detector (`content_sha256`) would stop working
as-is. Use the mirror for reading, sharing and cloud-agent access; treat the repo as the
graph of record.

**Slug legend (mirror-only).** `hypergraph push --legend` emits the body of a
dedicated legend node — a table mapping each diverged local slug to the slug
Flywheel minted for its mirror copy — so mirror readers can resolve locally-minted
provenance. The skill layer regenerates it on every push: commit it as a node titled
exactly `Hypergraph mirror slug legend`, parented to the mirror's *record* root
(locate an existing one among the root's children by title; lease + commit to
update, create otherwise). The legend lives only on the mirror: it has no local node
file, mirrored node bodies are never rewritten to reference it (byte-identity holds),
and both `import` and `push --verify` exclude it by its title. For an adopted project
the same table is the **archive→mirror map**: an imported node keeps its archive slug
as its local slug, so the "local slug" column reads as the archive slug.

**Archive lineage (adopted projects).** `hypergraph push --lineage` emits the body for
the mirror's **record root**, rendered from the config `archive:` block plus a count of
node files carrying `origin:`. It names each archive root (slug, node_id, title), says
the archive is frozen and never written to, and states plainly that artifacts stayed
behind. The skill layer commits it as the root's body — the first thing a mirror reader
sees — on adoption, and refreshes it on reconcile when `archive:` changes. It errors
(exit 2) when the config has no `archive:` block, so a mode-B project simply never calls
it. Mirror root titles stay plain — `<project> — record`, `<project> — state`; the
mirror-and-lineage facts live in this body, not in the title.

**Drift detection.** `hypergraph push --verify --against <export.json>` diffs a
fresh mirror export (`flywheel_export_subgraph` over **this project's own mirror
roots only**, `include_descendants: true`) against the local node files — read-only,
exit 1 on any drift, `check`-style DRIFT report. Never splice the archive roots into
that export: a mode-A mirror that holds almost none of the graph verifies clean when
you do, because the imported nodes' archive-owned ids resolve through the spliced
subgraph. Mirror-only structure is exempt: the legend node (by title) and any roots
declared under `mirror_roots:` in config — adopted projects mirror under fresh roots
that have no local counterpart, so those root ids are read from config. It flags: local nodes never pushed or missing
from the export, body-hash mismatches, summary mismatches, local edits pending push
(`flywheel.content_sha256` vs current body), and revision skew between the export
and each file's `flywheel:` block. The reconcile skill runs it after every push
(step 8). Local files are canonical — drift is fixed by re-pushing or investigating
the foreign write, never by editing local nodes to match the mirror.

## Failure handling

- All local-backend errors exit **2** with a one-line `error:` on stderr; `check` keeps
  its own 0/1 contract. `push --plan` exits 1 when the plan carries violations.
- Structural problems are caught on load, not silently tolerated: slug not matching
  `SLUG_RE`, filename ≠ frontmatter slug, duplicate `node_id`, missing or unparseable
  `created_at` (the unreconciled/HWM partition is timestamp-ordered), a parent slug with
  no node, malformed frontmatter.
- Concurrency: single-writer by protocol, `--expect` by mechanism, git by substrate.
  Two agents reconciling at once produce a merge conflict in `.hypergraph/graph/state/`,
  which is the honest outcome — resolve it in git, then re-`export` and `check`.
