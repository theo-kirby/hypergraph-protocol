---
node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
slug: weathered-union-7494
title: Publication
created_at: '2026-08-07T17:25:37.632552+00:00'
parents:
- cool-king-8586
summary: Parked by Operator (no date); v0.1 gate met with four unreleased changes; distribution proven an allow-list — research/ ships nothing.
flywheel:
  node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
  slug: weathered-union-7494
  revision: 13
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 44f61fe3d778bca74a865d9cac61f56538e9fef32c5fd5a5a9134c70346fa525
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: open

## Current

Publication shape decided [rec: damp-mountain-8757]: spec-first (SPEC.md is the durable artifact), a PyPI CLI package as the distribution vehicle (CLI will also install the skills into adopter projects), this repo as reference implementation + self-dogfood exhibit — adopters never clone or fork it; optionally a Claude Code plugin as a secondary channel. The existing Flywheel graphs continue unchanged through the rename — an export/import fork would re-slug nodes and sever cross-graph provenance [rec: damp-mountain-8757].

Name claimed on both registries: `hypergraph-protocol` on PyPI (0.0.1 at claim time [rec: damp-mountain-8757]) and on npm (placeholder 0.0.2 pointing users to PyPI, published under the `kirbyt` account [rec: lively-willow-7648]). GitHub repo renamed to theo-kirby/hypergraph-protocol (old URL redirects).

Release 0.0.2 is live on PyPI and verified from the public index [rec: crisp-lake-4496] [rec: rough-reef-5869]: `hypergraph skills install` installs all five skills (skills + `templates/agents-block.md` as package data via hatchling force-include; project-level `.claude/skills/` default, `--user` for `~/.claude/skills`), and the published CLI's epoch-aware `check` reports 0 violations on both adopted repos. The distribution story is end-to-end: an adopter needs only uvx + PyPI. Both adopter repos' onboarding un-pinned from the dev checkout [rec: rough-reef-5869].

Licensed MIT [rec: lively-willow-7648]: LICENSE committed, PEP 639 metadata in pyproject (`license`/`license-files`), LICENSE in the sdist; rebuilt 0.0.2 artifacts twine-clean. The already-published PyPI 0.0.2 predates the metadata — the next release carries it.

Repo is PUBLIC [rec: lawful-birch-4414]: main pushed, visibility flipped after a second full-history gitleaks scan (43 commits, no leaks; `.env` confirmed untracked with no history). GitHub auto-detects the MIT license; unauthenticated fetch returns 200 — the PyPI/npm repository links now resolve for outsiders.

Remaining (the gap): spec-first announcement (venue and wording are the Operator's call). The v0.1 package gate for general adoption is the git-native backend (see empty-forest-6305) [rec: damp-mountain-8757].
- **Parked by Operator directive** (2026-08-08): the 0.1.0 release and the spec-first announcement are both pending Operator decisions with **no date**, and no agent work proceeds on either. Recorded for when it resumes — the v0.1 gate (git-native backend) is met, and four changes are shipped but unreleased: MIT/PEP 639 metadata (absent from the published 0.0.2), fork-import, the `verify` mirror_roots exemption, and the mode-B epoch marker fix. The evidence for the announcement is being built first, as the protocol benchmark (protocol-benchmark-4417) [rec: southern-ridge-1802].
- The distribution/repo boundary is measured rather than assumed: publishing is an **allow-list**, not the repo. Both artifacts were built — the wheel is 40 files / 415 KB (`hypergraph_protocol.py` + skills + templates + dist-info), the sdist 14 files — so `tests/`, `.hypergraph/`, `STATE.md`, `AGENTS.md` and the new `research/` tree all ship nothing, and `tests/test_packaging.py` fails if any is added to either hatchling include list. Incidentally re-verified: the published 0.0.2 installs on a bare cloud box via `uv tool install hypergraph-protocol` + `hypergraph skills install --user` [rec: twilight-wood-1934].

- Version **0.0.3** in the tree, unreleased: the two `check` fixes (missing-config error, root-inference warning) and `--version` [rec: staid-field-2723]. `tests/test_packaging.py` now holds `tools/hypergraph.py`'s `__version__` in step with pyproject, because the benchmark's arm-C boxes install `hypergraph-protocol==0.0.3` pinned and assert the reported version on the box — `uv tool install` reuses a cached tool, and would otherwise leave a box silently running an older build while the write-up named this one [rec: staid-field-2723].
- **Release 0.0.5 is live on PyPI and verified from the public index** [rec: long-peak-1620]. It clears everything that had accumulated unreleased — the MIT/PEP 639 metadata absent from the published 0.0.2, fork-import, the `verify` mirror_roots exemption, the mode-B epoch marker fix, the two `check` fixes and `--version` from 0.0.3, the whole mirror-opacity change in 0.0.4, and the merge-safety work in 0.0.5. A clean venv installing from PyPI reports 0.0.5, resolves `hwm` and `check --since`, and lays down all five skills.
- The release had a dependency running the other way: the shipped adopter CI template calls `check --since`, which does not exist before 0.0.5, so until this release anyone copying it got a workflow that could not run [rec: long-peak-1620].
- The repository's main branch now matches the release — 14 local commits pushed, closing a window where a published artifact's source was not public [rec: long-peak-1620].
- Still parked on an Operator decision with no date: the spec-first announcement, and the npm placeholder still pointing at PyPI 0.0.2 [rec: southern-ridge-1802] [rec: long-peak-1620].
- **Release 0.0.6 is live on PyPI and verified from the public index** [rec: sleepy-vine-2805]. It carries the adoption fixes, which is what made it urgent rather than routine: 0.0.5 handed every adopter the step order that hard-errors, so the only working path was a checkout of this repo — the distribution shape this project rejected at the start. Verified with the published CLI alone in a scratch repo: five skills installed, the installed adopt skill carries the staged interview, `--survey` printed Timeline signals, and authoring a root then running `adopt --init` printed `(adopted existing)` and checked 0/0.
- **0.0.7 is live on PyPI** [rec: humble-rain-0304], carrying `hypergraph upgrade` and the `hypergraph_version:` stamp. It had to ship rather than wait: the upgrade path only functions once a release contains it, so leaving it unreleased was the same defect restating itself. The version now lives in five places and two parity tests keep them in step.
- Version parity is guarded in three places now, and the third fired on this release: `test_spec_header_matches_pyproject` failed with `SPEC.md says v0.0.5, pyproject says 0.0.6` on a release where SPEC.md itself did not change [rec: sleepy-vine-2805].
- **The README front door now matches the distribution.** Quickstart opened with `./install.sh — symlink the skills into ~/.claude/skills`, which requires cloning this repo — the one thing this node has said since the shape was decided that adopters never do; the real path (`uv tool install hypergraph-protocol` + `hypergraph skills install`) appeared nowhere, and adopt was prose after the quickstart. There is now an `## Install` section before Quickstart, two labelled routes (new project → init, existing → adopt), bare `hypergraph` in every adopter-facing command block, and `./install.sh` demoted to a dev-checkout note. A doc test asserts the install lines, because that is the claim that went stale [rec: patient-sail-0175].

**What the project says it is has changed, everywhere it is said** [rec: clever-ledge-6588]. It was "a protocol for keeping research projects legible to fresh agents" — a description of the mechanism, not of the goal. It is now a **substrate for autonomous research and engineering**: the memory layer an agent needs to carry work across months and contexts without a human holding the thread, aimed at a structural failure rather than a capability one, because a chat log is not memory, a codebase records only what was kept, and a task list rots. The name is explained rather than asserted — a claim answers to many pieces of evidence and a piece of evidence bears on many claims, so the citations join sets to sets across two graphs. And the two halves are separated by maturity **in public**: the record graph is established practice, an append-only causal log being a lab notebook under another name, while the state graph and the cross-graph structure that falls out of it are the novel half and under active development, with whether the projection stays small and honest as its evidence base grows without bound named as the open research question. README, SPEC, AGENTS.md, the CLI docstring, the package description and the shipped agents-block all carry it.

**0.0.8 is published and verified from the public index** [rec: patient-ridge-8464]. Verification used published artifacts only, never `dist/`: `uv tool install --force --refresh` moves 0.0.7 → 0.0.8, the released package's `hypergraph skills install` lands an adopt skill carrying both the mode A walkthrough and the authoring-traps section, and `upgrade --dry-run` run from the published binary against cadex's customized AGENTS.md block reports it and steps back where 0.0.7 deleted it. The index summary carries the new framing, so "a substrate for autonomous research and engineering" is what the package advertises.

**0.0.8 is now consumed from the public index by a repo with no path to this source tree** [rec: lean-field-0101]. `hypergraph-labs` declares `hypergraph-protocol==0.0.8` as an ordinary dependency, installs the CLI with `uv tool install`, and bakes the same pin into the container image its experiments run in. That is the adoption route this node has described since the shape was decided, exercised by someone who cannot fall back to a checkout — and it means every future benchmark run also tests whatever was actually published.

## Negative knowledge

- [scope: naming/distribution of this project | confidence: high | evidence: damp-mountain-8757] Bare `hypergraph` is taken on PyPI; `hg*` names read as Mercurial (its CLI is `hg`); clone/fork distribution rejected — the protocol is an overlay on adopters' repos, not a template.
- [scope: publishing to npm with a token from a dotenv file | confidence: high | evidence: lively-willow-7648] `source .env` sets but does not export variables — `${VAR}` in .npmrc expands empty in the npm child process and the PUT fails as E404 (not 401), which misreads as a registry problem. Wrap the source in `set -a` … `set +a`.

## Provenance

- patient-ridge-8464 — 0.0.8 published; the release verified against PyPI rather than the build directory
- clever-ledge-6588 — the goal restated as an auto-research substrate, and the record/state maturity split published
- damp-mountain-8757 — publication shape + name decision; executed PyPI 0.0.1 publish, GitHub rename, gitleaks-clean history check
- vast-sky-3964 — 0.0.2 scope: skills install + agents-block template as package data
- crisp-lake-4496 — 0.0.2 built, twine-clean, wheel-verified; publish blocked on credentials at the time
- rough-reef-5869 — 0.0.2 published and index-verified; adopters un-pinned
- lively-willow-7648 — MIT license + PEP 639 metadata; npm name claimed with a PyPI-pointing placeholder
- lawful-birch-4414 — main pushed, repo flipped public after gitleaks-clean re-scan; MIT auto-detected
- southern-ridge-1802 — Operator directive parking the release and the announcement
- twilight-wood-1934 — packaging boundary measured empirically; published 0.0.2 re-verified on a fresh box
- staid-field-2723 — 0.0.3 in tree (checker fixes + `--version`); version parity pinned by test
- long-peak-1620 — 0.0.5 released to PyPI and verified from the public index
- patient-sail-0175 — README front door corrected to the PyPI path; adopt promoted to a first-class quickstart route
- sleepy-vine-2805 — 0.0.6 released and index-verified; the adoption fixes reach adopters
- humble-rain-0304 — 0.0.7 released; the upgrade path reaches adopters
- lean-field-0101 — the published 0.0.8 consumed as a plain PyPI dependency by a repo with no access to this checkout
