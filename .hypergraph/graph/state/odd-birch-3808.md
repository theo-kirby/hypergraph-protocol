---
node_id: abe5a44c-0383-5a78-958e-0c3606a40905
slug: odd-birch-3808
title: PyPI releases
created_at: '2026-08-14T13:25:06+00:00'
parents:
- damp-basin-8974
summary: 0.0.2 through 0.0.8 live and each verified from the public index; the published package is a plain dependency of an external repo; 0.9.0 staged and deliberately unpublished — the publish is the Operator's step.
flywheel:
  node_id: fc3ca91a-1b5d-5543-921b-b82d222f75ec
  slug: polished-sky-8897
  revision: 2
  pushed_at: '2026-08-16T18:25:04+00:00'
  content_sha256: 0a0b20017b7bc5aa2cb5e57e736f6d5fd854c2d5ee7bd4a4556b5c2a39309433
  parents_sha256: 9c8039d8ccc995d9c15665648d7d82c9399050ef076f05102c409e2d18ebabfb
  parents:
  - e6697aa9-2f7c-5b23-8ef4-abc687d15567
---
Status: working

## Current

Five releases are live on PyPI, and every one was verified **from the public index** rather than from `dist/` — the check that distinguishes "built" from "shipped" [rec: patient-ridge-8464].

- **0.0.2**, the first real one: `hypergraph skills install` lands all five skills (skills plus `templates/agents-block.md` as package data via hatchling force-include), and the published CLI's epoch-aware `check` reports 0 violations on both adopted repos. Both adopters were un-pinned from the dev checkout in the same pass, which is what made the distribution story end-to-end: an adopter needs only uvx and PyPI [rec: crisp-lake-4496] [rec: rough-reef-5869].
- **0.0.5** cleared everything that had accumulated unreleased — the MIT/PEP 639 metadata absent from the published 0.0.2, fork-import, the `verify` mirror_roots exemption, the mode-B epoch marker fix, the two `check` fixes and `--version`, the mirror-opacity work, and the merge-safety work. It had a dependency running the other way: the shipped adopter CI template calls `check --since`, which did not exist before this release, so until it shipped anyone copying that workflow got one that could not run [rec: long-peak-1620].
- **0.0.6** carried the adoption fixes, which made it urgent rather than routine: 0.0.5 handed every adopter the step order that hard-errors, so the only working path was a checkout of this repo — the distribution shape this project rejected at the start [rec: sleepy-vine-2805].
- **0.0.7** carried `hypergraph upgrade` and the `hypergraph_version:` stamp. It had to ship rather than wait, because an upgrade path only functions once a release contains it; leaving it unreleased was the same defect restating itself [rec: humble-rain-0304].
- **0.0.8** was verified with published artifacts only: `uv tool install --force --refresh` moves 0.0.7 → 0.0.8, the released package's skills carry the mode A walkthrough, and `upgrade --dry-run` run from the published binary against cadex's customized AGENTS.md block reports it and steps back where 0.0.7 deleted it [rec: patient-ridge-8464].
- **The published package is now consumed by a repo with no path to this source tree.** `hypergraph-labs` declares `hypergraph-protocol==0.0.8` as an ordinary dependency and bakes the pin into the container image its experiments run in, so every run of it is also a test of what was actually published [rec: lean-field-0101].
- **0.0.9 was staged by the viz cut and never published** [rec: loyal-tide-3608]; **0.9.0 supersedes it as the staged release** [rec: shady-garden-2130]. The clean-slate version: substrate + skills + dispatch as one product, the mirror's networked half in its own module, `heal` folded into `upgrade --graph`. All five stamps moved in one commit under the parity tests, and both healers' `since` republished as 0.9.0 because 0.0.9 never reached the index. `uv build` succeeds and `hypergraph --version` reports 0.9.0; the publish to PyPI — and its verify-from-the-public-index step — is the Operator's call and has not run.
- **Version parity is guarded in three places and the third has fired**: `test_spec_header_matches_pyproject` failed with `SPEC.md says v0.0.5, pyproject says 0.0.6` on a release where SPEC.md itself did not change [rec: sleepy-vine-2805]. The version lives in five places with two parity tests holding them in step [rec: humble-rain-0304], and the benchmark's boxes pin an exact version and assert it on the box, because `uv tool install` reuses a cached tool and would otherwise leave a box silently running an older build [rec: staid-field-2723].

## Negative knowledge

- [scope: publishing to npm with a token from a dotenv file | confidence: high | evidence: lively-willow-7648] `source .env` sets but does not export variables — `${VAR}` in .npmrc expands empty in the npm child process and the PUT fails as E404 (not 401), which misreads as a registry problem. Wrap the source in `set -a` … `set +a`.

## Provenance

- crisp-lake-4496 — 0.0.2 built with skills install as package data
- rough-reef-5869 — 0.0.2 published and index-verified; adopters un-pinned
- long-peak-1620 — 0.0.5 released; the CI-template dependency that ran the other way
- sleepy-vine-2805 — 0.0.6 released; the adoption fixes reach adopters; the third parity guard fires
- humble-rain-0304 — 0.0.7 released; the upgrade path reaches adopters
- patient-ridge-8464 — 0.0.8 published and verified against the index rather than the build directory
- lean-field-0101 — the published 0.0.8 consumed as a plain dependency by a repo with no access to this checkout
- staid-field-2723 — the version pin the benchmark boxes assert, because uv tool install reuses a cached tool
- loyal-tide-3608 — 0.0.9 staged by the viz cut; not yet published
- shady-garden-2130 — 0.9.0 stamped in all five places and staged, deliberately unpublished
