---
node_id: 9bbe785c-d63f-5769-ad82-35b3b349d7a5
slug: tender-moss-3792
title: 'Fork-import shipped: origin/flywheel identity split, import --fork, push --lineage'
created_at: '2026-08-08T09:51:56+00:00'
parents:
- copper-moss-3669
summary: ''
flywheel:
  node_id: d403396a-a778-57f7-8351-a500887663f3
  slug: damp-fire-6999
  revision: 0
  pushed_at: '2026-08-08T11:35:36+00:00'
  content_sha256: 8cd89ffa1bb842ec56c5d37452f827f55d44b191678c37d10d79606c22a6194f
---
## What

Shipped fork-import: the `origin:` / `flywheel:` identity split, `import --fork`,
`push --lineage`, a push scale guard, and the doc/skill changes that make an adopted
project mirror its whole history. Tooling and prose landed together, in one commit.

## Why

Executes the design recorded in `copper-moss-3669`. Nothing about the diagnosis changed
during implementation; two details were corrected against the live tooling (see Result).

## Method

`tools/hypergraph.py`:

- `FM_ORDER` gains `origin` immediately before `flywheel` — position only;
  `render_node_file` already passes unknown keys through.
- `cmd_import` takes `--fork`. With it, the node file gets
  `origin: {backend, node_id, slug, revision?, exported_at}` and **no** `flywheel:`
  block; without it, behaviour is byte-identical to before. The default had to hold:
  plain `import` still serves re-homing a graph you own while continuing to mirror to
  it (`backend/local-adapter.md`, "Bootstrapping from Flywheel") — this repo did
  exactly that, and dropping `flywheel:` there would duplicate the whole graph on the
  next push. `origin:` deliberately carries no `content_sha256`: it is provenance, not
  a change detector.
- `lineage_content(graph_dir, config)`, beside `legend_content`. Renders the mirror
  record root's body from the config `archive:` block plus a count of node files
  carrying `origin:` (falling back to `archive.imported`). Names each archive root
  (slug, node_id, title), states the archive is frozen and never written to, and says
  plainly that artifacts stayed behind. Raises `LocalGraphError` (exit 2) when
  `archive:` or `archive.roots` is absent, so a mode-B project simply never calls it.
- `cmd_push` gains `--lineage`, mirroring the `--legend` branch (stdout or `-o`).
- Scale guard: `PUSH_CREATE_WARN = 200`. `push --plan` prints a stderr warning above
  it, naming incremental result-recording and epoch-split. Warning only — exit code
  unchanged.
- `legend_content` gains two header lines: for an imported node the local slug *is*
  the archive slug, so the table doubles as the archive→mirror map.

No logic change to `push_plan` or `verify_mirror`. With `flywheel:` absent, an imported
node is planned as a `create`, parents-first, like any authored node. `check` reads
neither block, so I1–I8 are untouched — asserted directly by a test that exports a
plain import and a forked import and compares the node lists.

`tests/test_local_backend.py`: 62 → 72 tests. New "fork import" section covers
`--fork` frontmatter shape and key order, archive `revision` preservation, re-import
with `--fork --force` replacing `flywheel:` with `origin:`, a forked plan producing one
create per node parents-first, `check` unchanged by `origin:`, a clean `verify` against
a **mirror-roots-only** export after a full push (asserting no archive anchor is in the
export), the legend as archive→mirror map, `push --lineage` rendering and its error
without an `archive:` block, and the create-threshold warning. The existing
`test_import_preserves_flywheel_identity_and_is_idempotent` gained
`assert "origin" not in meta` as the regression guard on the default.

Docs and skills:

- `SPEC.md` *Adoption epochs*: a full import **is** a fork; the project re-publishes
  its whole imported history to a mirror it owns; the archive stays frozen and is the
  artifact pointer only; verification runs against the project's own roots alone; the
  mirror projects the repo, never the archive. *Per-project files* now describes the
  node files and both frontmatter blocks, and says `archive:` feeds `push --lineage`.
- `backend/local-adapter.md`: "Bootstrapping from Flywheel" split into the re-home case
  (no `--fork`) and the adopt case (`--fork` mandatory), with the two silent failure
  modes stated in both directions; frontmatter example gains `origin:`; mirroring
  section gains incremental result-recording and the archive-lineage paragraph; the
  drift-detection paragraph now says export the project's own mirror roots only and
  why, replacing the line that claimed the archive holds the legacy mirror.
- `backend/flywheel-adapter.md`: new §10a re-parenting recipe — add-then-remove so the
  node is never parentless, all four optimistic-lock revisions, re-read between calls
  because the add bumps the child's revision, graph-write budget, prove on one node
  first.
- `templates/config.example.yml` (symlinked into the init and adopt skills): `archive:`
  documented as the `push --lineage` source, with `title` per root, `imported`, and
  `artifacts`.
- `skills/hypergraph-adopt/SKILL.md`: step 2 mode A uses `import --fork` (mandatory);
  step 5 rewritten — plain mirror root titles, `push --lineage` as the mirror record
  root's body, push the whole graph, **record results in batches of ~20**, verify
  against `mirror_roots:` alone.
- `skills/hypergraph-reconcile/SKILL.md` step 8: refresh the lineage node alongside the
  legend when `archive:` changes; verify against the project's own roots, never with
  archive anchors spliced in.
- `skills/hypergraph-init/SKILL.md`: the bootstrap note retitled to the re-home case
  and told explicitly not to pass `--fork`.
- `README.md`: the adoption paragraph now describes full-history mirroring.

## Result

`uv run pytest tests/` — **72 passed**. `check` on this repo — **0 violations, 0
warnings** (3 I5 info lines for the unreconciled M0 node and its two pending impacts).

Two corrections against the live tooling, neither affecting the design:

1. The re-parenting tools are named `flywheel_add_parent` / `flywheel_remove_parent`
   (MCP) and `flywheel nodes:add-parent` / `nodes:remove-parent` (CLI) — not the
   `*_add_node_parent` form the plan assumed. Verified against
   `flywheel help --format=json` and the installed Flywheel skill tool maps. `add_parent`
   was already cited in adapter §2 for multi-parent creates; §10a keeps that spelling.
2. `lineage_content` renders archive titles through a pre-computed local rather than a
   backslash escape inside an f-string expression, which only parses on Python 3.12+
   while the script declares `requires-python = ">=3.10"`.

The behaviour change is confined to `import --fork`. Existing adopted repos are
unaffected until they re-import; a3go's migration is the next step, and is the first
case where `push --verify` will check a mode-A mirror on its own merits.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 2daccbfe5d06e73592a5a2ffc4ee4e46c094e90f

## State Impact

- target: wandering-sun-8831 — new claims: import --fork writes origin: and omits flywheel:, so push plans every imported node as a create; push --lineage renders the mirror record root body from config archive:; push --plan warns above 200 creates. Test count 72
- target: blue-sun-8921 — identity split landed: origin: is immutable archive provenance (read by nothing), flywheel: is this project's own mirror identity (written only by push --record-result); local-adapter documents the two silent failure modes and mirror-roots-only verify; flywheel-adapter §10a adds the re-parenting recipe
- target: dry-wildflower-2260 — hypergraph-adopt mode A now imports with --fork, pushes the whole graph under plain-titled mirror roots with push --lineage as the record root body, records results in batches of ~20, and verifies against mirror_roots alone; reconcile step 8 refreshes lineage; init clarifies --fork is not for re-homing
- target: morning-crane-7863 — fork-import tooling, docs and skills shipped; field migration of a3go is the remaining step
