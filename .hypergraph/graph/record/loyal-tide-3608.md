---
node_id: 1b83983f-152d-5566-9f10-8e35fdcc7a3b
slug: loyal-tide-3608
title: 'The viz cut: visualization leaves core, the JSON exports become the contract'
created_at: '2026-08-16T16:34:36+00:00'
parents:
- wise-river-3571
summary: ''
flywheel:
  node_id: 8fd5c745-0ec9-5833-a0be-6a7ac4798a9d
  slug: billowing-frost-0232
  revision: 0
  pushed_at: '2026-08-16T16:38:33+00:00'
  content_sha256: 5898974b9a0339506e9207c801bd71ce853ec1d131d4ce3dae23d5374d806218
  parents_sha256: 7c19b01e6ecb2afaf7392b1714c7d29d5bc99dd756a1d7bc04bbc4142f7afeec
  parents:
  - f6b6de60-6126-5155-b7c0-3213b995beb2
---
## What

Removed visualization from the core tool. `tools/hypergraph.py` drops from 12,599
to 8,376 lines (−4,223, 34%): the viz section (layout engine, payload assembly,
excaligraph spec emitter, `cmd_viz`), the ~3,700-line embedded page template, the
page sources (`tools/viz/`), the bundler (`tools/bundle_viz.py`), the viz test
suite (`tests/test_viz.py`), the playwright browser baselines (`tests/browser/`),
and the two fixtures that existed only for them (`tools/fixtures/{self,large}`).
`hypergraph viz` remains as a signpost only: it prints where visualization went
and exits 2. Version stamps move to 0.0.9 (pyproject, `__version__`, SPEC header,
both config stamps); playwright leaves the dev group; the sdist allow-list no
longer ships viz sources.

The contract that replaces it: the JSON exports. `export` writes
`.hypergraph/cache/{record,state}.json`, and any renderer that reads those files
can draw the graphs. The planned consumer is **hypergraph-viz**, a thin
npm-ecosystem translator built on excaligraph (which already exists, standalone,
with native hyperedge blobs and a conformance harness against Excalidraw's own
`restore()`). The `viz:` block in `.hypergraph/config.yml` stays legal as display
configuration for that external tooling; core never reads it.

## Why

Operator decision, this session, after a commissioned adversarial audit of the
whole project. The audit measured the file: the interactive page and its template
were ~33% of the tool, the largest single block in it, serving a capability the
protocol itself never references — no invariant, no skill, no workflow touches
`viz`. The settled restructuring: hypergraph-protocol stays the substrate
(graphs, invariants, checker, storage); visualization becomes external tooling
consuming the same exports the checker consumes; excaligraph stands alone as a
general library; the Flywheel mirror becomes an optional extra in a later cut;
the autonomous-operation layer (working name: taxa) becomes a separate package.
The viz cut is deliberately the first cut because it has the cleanest seam: the
exports already were the integration surface (backend/local-adapter.md names
them as such), so nothing downstream changes.

The trade was named and accepted: the interactive page (force layout, live mode,
five views) is capability lost from this repo, not moved — Excalidraw scenes are
static but hand-editable. Git history at fbf18f2 keeps the page recoverable if
hypergraph-viz wants to absorb it.

## Method

Cut by section markers, bottom-up so line indices stayed valid: the CLI `p_viz`
block replaced with a two-line stub registration, the generated template block
(`# --- BEGIN GENERATED VIZ TEMPLATE ---` … `# --- END ---`) deleted, the viz
section replaced with a 5-line `cmd_viz` signpost. Verified no viz helper
(`kebab`, `layered_layout`, `build_viz_data`, `viz_payload`, `render_viz`,
`assemble_viz_template`) had a caller outside the cut ranges before cutting.
Swept every doc for stale references: README (viz sections replaced with the
external-contract section), SPEC Tooling (rewritten: "Visualization is not part
of this tool"), backend/local-adapter.md (integration-surface and artifacts
paragraphs), AGENTS.md, the config comment. The skills' `references/spec.md`
symlinks picked the SPEC edit up for free. Two surviving tests touched viz:
the offline-transport sweep in test_mirror.py now asserts the stub exits 2
without reaching for a transport, and test_local_backend.py drops the
`build_viz_data` payload test (its surviving claim — state nodes carry no
artifacts — is still asserted by `test_new_state_refuses_an_artifact`).

## Result

`uv run pytest tests/`: 283 passed, 2 skipped (the env-gated live-mirror pair),
0 failed — down from 300 collected before the cut, with every removed test being
a test of removed code. The packaging suite's version-stamp tests caught all
three stamps, which is what they are for. `hypergraph viz` exits 2 with the
signpost; `--help` and every other subcommand unchanged. The core tool now
contains no HTML, no JS, and no browser dependency anywhere in the dev group:
checker + renderer + storage + mirror, which is what the package claims to be.
0.0.9 is staged but not published; the PyPI release is its own step.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: fbf18f24f2648e9d37084ac6f551c1314e90923b

## State Impact

- target: polished-pond-2718 — the in-core visualizer is removed at 0.0.9; rewrite as the visualization seam: JSON exports are the contract, `viz` is a signpost stub (exit 2), the `viz:` config block belongs to external tooling; status working → open, because the capability is currently a contract whose consumer (hypergraph-viz) does not exist yet
- target: brave-bramble-9399 — status working → superseded: the page machinery (template, bundler, sources, browser baselines, viz fixtures) left the repo with the cut; recoverable from git history at fbf18f2
- target: lawful-ash-6222 — status working → superseded: the five views left with the page; the job they did passes to hypergraph-viz when it exists
- target: wandering-sun-8831 — new claim: the tool drops from 12,599 to 8,376 lines (−34%) with no HTML, JS or browser dependency left; suite 283 green with playwright out of the dev group
- target: odd-birch-3808 — new claim: 0.0.9 staged (stamps bumped, sdist allow-list without viz sources) but not yet published; the release is its own step
