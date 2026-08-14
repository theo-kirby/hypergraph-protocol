---
node_id: 98f8a6ad-1ff7-5ea2-8542-333d356dc27a
slug: humble-rain-0304
title: 'Released 0.0.7: the upgrade path reaches adopters'
created_at: '2026-08-09T16:29:41+00:00'
parents:
- ancient-bluff-9706
summary: 0.0.7 live on PyPI; the two-command update verified with published artifacts only.
flywheel:
  node_id: c8d4ea51-4515-51b0-afee-cb897c419377
  slug: quiet-dawn-8697
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: d86294977d4e69f115d74ebf24db216072f2a33f1a9771bdb3dc29b9d03259e4
  parents_sha256: 11cce0818ea8a96fa6d86a9bff73b4cbc14940c15d74c4dde316480c2ba88fad
  parents:
  - e6c36460-89a4-53fa-b98b-ca36548672b9
---
## What

Released **0.0.7** to PyPI, carrying `hypergraph upgrade` and the
`hypergraph_version:` stamp [rec: ancient-bluff-9706].

## Why

Follows the upgrade work directly, and for the reason that work exists: the upgrade
path only functions once a release contains it. Leaving it in the tree at 0.0.6 was
the same defect restating itself — an adopter cannot run a command that is not in the
artifact they installed.

## Method

Same release drill as 0.0.6. The version now lives in **five** places — pyproject,
`__version__`, SPEC.md's header, this repo's config stamp, and the config template —
and the two parity tests added with the stamp are what make that safe to say: bump,
run the suite, and anything left behind fails loudly rather than shipping.

290 → 307 tests green → `uv build` → `uvx twine check` (both PASSED) → 25 `skills/`
entries in the sdist → commit and push main → `uv publish --token`.

## Result

Verified with **published artifacts only**, simulating the adopter this feature is
for: installed `hypergraph-protocol==0.0.6` into an isolated tool dir, ran `skills
install` in a scratch repo, and wrote an AGENTS.md with an old sentinel block and a
config stamped 0.0.6 — the exact shape of a repo adopted last week. Then ran the two
documented commands:

- `uv tool install hypergraph-protocol==0.0.7` → `hypergraph --version` reports 0.0.7;
- `hypergraph upgrade` → refreshed all five skills, replaced the AGENTS.md block
  (the adopter's own prose above it intact, verbatim), and re-stamped the config to
  0.0.7.

The installed adopt skill went from 0.0.6's copy to 0.0.7's, which is the thing that
was impossible before this release: a fix to a skill can now reach a repo that already
adopted, without anyone re-running adopt or being told to.

Publication gaps unchanged: the spec-first announcement is still parked on an Operator
decision with no date, and the npm placeholder still points at PyPI 0.0.2.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 77cdb2545587d40bad199d8e56d423692d232c8d

## State Impact

- target: fond-sail-3288 — status open → working: the upgrade path is in a published artifact, verified end-to-end from PyPI with the two documented commands
- target: weathered-union-7494 — 0.0.7 published and index-verified
