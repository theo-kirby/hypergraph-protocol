---
node_id: ea4c9edf-af82-5db0-b87d-e62b9e342902
slug: old-dawn-8747
title: Local git-native backend landed; this repo's graphs migrated into the repo
created_at: '2026-08-07T18:14:12+00:00'
parents:
- patient-limit-9007
summary: 'Second adapter behind INTERFACE.md: node files are the source of truth, Flywheel a regenerable mirror. This repo migrated with identity preserved; STATE.md regenerates byte-identical offline.'
flywheel:
  node_id: e701dbbc-f23c-5306-9896-0f98835a4d0f
  slug: purple-dawn-2034
  revision: 0
  pushed_at: '2026-08-07T18:21:35+00:00'
  content_sha256: 17a1724bae20502e923a8cf2975ad81df01607ea0bb9f049f78b9a017a39b756
---
## What

Built the local (git-native) backend — the second adapter behind
backend/INTERFACE.md — and migrated this repo's own two graphs onto it. Markdown
files under `.hypergraph/graph/{record,state}/<slug>.md` are now the source of
truth; Flywheel is a regenerable mirror. This node was authored by the new
`hypergraph new record` CLI, into a file, with no MCP call anywhere in the path.

## Why

Executes the gap opened by the Operator directive in patient-limit-9007
(`empty-forest-6305`, Status: open). Two concrete costs were being paid: the
graph store was a hard dependency — without MCP, `check`/`render`/`viz` could
not run on this repo at all — and this project's memory lived off-site, so a
clone carried the code but not the record of how it got there.

## Method

The enabling observation: `check`/`render`/`viz` only ever read two JSON files
through one lenient loader (`load_graph`), which already accepts non-Flywheel
field aliases. So the local backend does not touch the checker, renderer, or
visualizer — it only has to emit the same JSON. That is the whole integration
surface.

Node format: YAML frontmatter (`node_id`, `slug`, `title`, `created_at`,
`parents` as **slugs**, `summary`, optional `flywheel:` mapping) then the body,
which is the node `content` byte-for-byte — no transformation, so every existing
parser works unchanged. `node_id = uuid5(HYPERGRAPH_NS, slug)`: deterministic,
reproducible from the files alone, no `uuid4` randomness. Slugs are minted
`adjective-noun-####` from two embedded wordlists, because `SLUG_RE` is what
every provenance line, `[rec:]` citation, impact target and HWM depends on.

Five subcommands in `tools/hypergraph.py` (single file, still `pyyaml`-only,
still network-free):

- `export` — node files → canonical JSON, ordered by `(created_at, node_id)`.
- `import` — graph-export JSON → node files, preserving source `node_id` and
  `slug_name` verbatim and stamping the `flywheel:` block. Idempotent.
- `new record|state` — mints the slug, generates `## Repo` (local `git` reads)
  and `## State Impact` / `## Provenance` from flags, then **runs the real
  checker over the candidate node before writing**: an impact target that
  resolves to no state node exits 2 with nothing written.
- `update` — INTERFACE op 7. `--print-sha` is the read half of the
  compare-and-swap; `--expect` refuses a stale write and leaves the file
  untouched; record nodes are refused outright (append-only).
- `push --plan` / `--record-result` — the mirror. Because the tool may not call
  MCP, it emits an ordered plan (creates topological, parents first, carrying
  `parent_flywheel_ids`; updates carrying `base_revision`; unchanged nodes
  omitted) which the skill layer executes, then folds the returned ids back into
  frontmatter.

I3 is now mechanical, not just documentary: `new state` and `update` refuse to
run without `--reconcile`.

Migration of this repo: `flywheel export:subgraph` on both roots (15 record, 10
state nodes) → `hypergraph import` → commit `.hypergraph/graph/`. Config gained
`backend: local`, `graph_dir:`, `mirror: flywheel`.

Also landed: `backend/local-adapter.md` (all 10 ops, symlinked into all four
skills' `references/`), a backend-dispatch step in each `SKILL.md` reading the
`backend:` key — which until now was declarative and read by nothing —
`tests/test_local_backend.py`, and the `tools/fixtures/local-graph/` fixture.

## Result

49 tests pass (16 pre-existing checker/viz + 33 new). The load-bearing one is
the round-trip: importing `tools/fixtures/clean/{record,state}.json` into node
files and exporting back yields node-for-node identical graphs (slugs, ids,
parents, content) that still pass `check` with 0 violations and 0 warnings.

Migration verified end-to-end and offline: `export` → `check` reports 0
violations, and `render` regenerates `STATE.md` **byte-identical** to the
committed file that was produced from the live Flywheel graph. `push --plan`
against the freshly imported graph is empty, confirming the mirror is in sync.
Because `import` preserved node_ids and slugs, the existing `record_root` /
`state_root` config, every provenance slug, and the high-water mark all stayed
valid — no identity divergence.

What this rules out: the claim that Hypergraph needs a hosted graph store. It
does not. Flywheel remains the recommended path when the graph must be reachable
by agents outside the working tree, and the two compose (`backend: local` +
`mirror: flywheel`), but the protocol now runs with nothing but a repo.

Deliberately deferred: artifacts (op 9) and tags (op 10), both optional and used
by no skill; slug translation on push, which would make the mirror non-identical
to source and complicate every update; bidirectional sync — git is the merge
substrate and Flywheel is a one-way projection.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 192a7ed1f7acbf9dec7f0cdf20ed865e04c2fc97

## State Impact

- target: empty-forest-6305 — status open → working: the git-native adapter exists, is documented (backend/local-adapter.md), tested, and is this repo's live backend
- target: blue-sun-8921 — INTERFACE.md now has two adapters, not one; op 7's concurrency story is explicit per adapter (Flywheel revision / local body-hash CAS); backend: in config becomes the live skill dispatch key
- target: wandering-sun-8831 — tools/hypergraph.py gains export/import/new/update/push; check/render/viz code paths untouched; test suite 16 → 49
- target: bold-field-1268 — self-host deepened: the graphs now live in the repo (25 node files committed) and this record node was authored by the new CLI with no MCP call
