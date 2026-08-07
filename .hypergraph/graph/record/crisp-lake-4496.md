---
node_id: 5b8cb71d-f950-5313-b141-c1281054b6c1
slug: crisp-lake-4496
title: 'M4: 0.0.2 built with skills install; PyPI publish blocked on credentials'
created_at: '2026-08-07T20:21:01+00:00'
parents:
- late-isle-6483
summary: 'skills install subcommand + skills/templates as package data; wheel/sdist twine-clean and verified end-to-end from the built wheel. uv publish failed: no PyPI token on this machine — Operator publish pending; M5/M6 proceed on repo-path CLI.'
flywheel:
  node_id: fea4cf57-1e03-529c-a738-115ac0b3cde2
  slug: solitary-water-7540
  revision: 1
  pushed_at: '2026-08-07T21:21:27+00:00'
  content_sha256: 147d9b0d1679d4ca1ce429314af61931826296c5b29c13c07408d62cf26a5680
---
## What

Built release 0.0.2 with the `hypergraph skills install` subcommand (adoption thrust M4): the five skills (including the new hypergraph-adopt) and `templates/` now ship inside the wheel as package data, installable into any repo with one command. The publish to PyPI itself is **blocked on credentials** — this machine has none (0.0.1 was published from the remote machine).

## Why

The distribution story before this: adopters could `uvx` the checker but had to clone the repo to get the skills — closing that gap is the standing Publication remainder (weathered-union-7494), and M5/M6 were meant to consume the published package as real adopters would.

## Method

`pyproject.toml` force-includes `skills/` and `templates/` into the wheel under `hypergraph_protocol_data/` (hatchling materializes the symlinked `references/` entries as real files at build time, so installed skills are self-contained); sdist gains `skills`, `templates`, `backend` so wheels built from it resolve the symlinks. New `skills_data_root()` finds the data dir next to the installed module or falls back to the repo layout, so the same code path works for `uvx` users and repo-path callers. `hypergraph skills install` copies each `hypergraph-*` skill into `./.claude/skills` (project default), `~/.claude/skills` (`--user`), or `--target DIR`; a destination that is a symlink (dev install.sh layout) is unlinked first rather than written through. Version bumped to 0.0.2 (pyproject + SPEC header). Test: install into a tmp dir, assert all five skills present and `references/spec.md` is a real file with SPEC content.

## Result

61/61 tests green. `uv build` clean; `uvx twine check dist/*` PASSED for wheel and sdist; end-to-end verification from the built artifact: `uvx --from ./dist/hypergraph_protocol-0.0.2-py3-none-any.whl hypergraph skills install --target <tmp>` installed all five self-contained skills. **Not done: `uv publish` failed — no PyPI token on this machine** (no ~/.pypirc, no keychain entry, no env credentials). The dist artifacts are committed-adjacent (dist/ is gitignored; rebuildable via `uv build`); the Operator can publish with `uv publish` once a token is present. Per the M4 fallback in vast-sky-3964's plan, M5/M6 proceed on the repo-path CLI. Commit 98d924b.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 98d924b7f2398f699940b2697d92ef7ad68d90f0

## State Impact

- target: morning-crane-7863 — M4 built and wheel-verified; PyPI publish pending Operator credentials; milestone list advances to M5
- target: weathered-union-7494 — skills install subcommand shipped (0.0.2 built, twine-clean, wheel-verified); the publish itself blocked: no PyPI token on this machine
