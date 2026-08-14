---
node_id: 38683f6a-e7ca-5add-a3bc-2912f637c3ba
slug: sleepy-vine-2805
title: 'Released 0.0.6 to PyPI: the adoption fixes reach adopters'
created_at: '2026-08-09T13:35:36+00:00'
parents:
- patient-sail-0175
summary: 0.0.6 live on PyPI, carrying the adoption fixes; verified end-to-end with the published CLI.
flywheel:
  node_id: f83cbf7d-ee33-5b30-808f-74e1766f22aa
  slug: rough-band-6937
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: b41b391570e0d19b70521756d3ec4bc2924653981adfc80f63d440510ec9ba29
  parents_sha256: 88d0be2291cb66fe1e426099f0a09d44417dfece7fa05c8c27d3e15cf6f6ec99
  parents:
  - 93da6620-6598-5ca5-8681-b6a488d02831
---
## What

Released **0.0.6** to PyPI on Operator instruction, carrying the adoption fixes
[rec: patient-sail-0175] — root-aware `adopt --init`, the 8-step workflow with the
staged interview, timeline signals in `--survey`, 3–10 prehistory nodes, and the
README front door. 0.0.5 shipped none of them, so an adopter installing from PyPI
still got the step order that hard-errors.

## Why

Follows the adoption fix, which landed unreleased by plan ("no release unless the
Operator calls for 0.0.6"). The Operator called for it: the fixes are worthless on
the shelf, because the adopter's entry point *is* the published package. The gap was
concrete — `uv tool install hypergraph-protocol` handed out the broken skill and the
pre-fix CLI, so the only working path was installing from a checkout of this repo,
which is the distribution shape this project rejected [state: weathered-union-7494].

## Method

Version bumped in `pyproject.toml` and `tools/hypergraph.py`. `tests/test_packaging.py`
caught the third place it lives — `test_spec_header_matches_pyproject` failed with
`SPEC.md says v0.0.5, pyproject says 0.0.6`, which is the guard doing its job on a
release where SPEC.md itself did not change.

Then: 290 tests green → `uv build` → `uvx twine check dist/*` (both PASSED) → both
artifacts inspected for the skills tree (25 `skills/` entries in each, the sdist
breakage of 0.0.5 not recurring) → commit and **push to main before publishing**, so
no window exists where a published artifact's source is not public → `uv publish
--token` from the repo `.env`.

Verification from the public index, not the build: `uv tool install` into an isolated
`UV_TOOL_DIR`. The unpinned `--refresh` install resolved to **0.0.5** on the first
attempt — index propagation lags the upload — and the pin `hypergraph-protocol==0.0.6`
got the real thing a moment later.

## Result

0.0.6 is live and correct on the public index. Verified with the published CLI alone,
in a scratch repo it had never seen:

- `hypergraph --version` → `hypergraph-protocol 0.0.6`;
- `hypergraph skills install` → all five skills, and the installed
  `hypergraph-adopt/SKILL.md` carries the staged interview (`Part 1 — History`), so
  the skill an adopter reads is the fixed one;
- `adopt --survey` printed **Timeline signals** with both a tag and a directory birth
  on a repo built to have one of each;
- **the ordering defect is gone in the shipped artifact**: authoring a record root
  first and then running `adopt --init` printed
  `record root: rising-marsh-2068 (adopted existing)` and wrote a valid config;
  `export` → `check` reported 0 violations, 0 warnings.

Publication gaps unchanged: the spec-first announcement is still parked on an Operator
decision with no date, and the npm placeholder still points at PyPI 0.0.2.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: dee0815f1c2c1a853a3b300f02af31c01e3bcfe8

## State Impact

- target: weathered-union-7494 — 0.0.6 published and verified from the public index; the adoption fixes are in the artifact adopters install, so the PyPI path no longer hands out the step order that hard-errors
