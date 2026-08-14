---
node_id: 0edbf452-02df-55b0-aee2-9813e677282a
slug: ancient-bluff-9706
title: 'Closed the update gap: hypergraph upgrade + a version stamp'
created_at: '2026-08-09T15:54:04+00:00'
parents:
- sleepy-vine-2805
summary: hypergraph upgrade refreshes an adopted repo's copies; hypergraph_version lets check detect skew.
flywheel:
  node_id: e6c36460-89a4-53fa-b98b-ca36548672b9
  slug: old-cake-0477
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: c66cfbecc463bd07ca11699915f2a062d38146c75881797091e852781ca8b2cd
  parents_sha256: e2557e38238a67c5be11b7c0682f58c95c20803b42f485010a8e14d4296e4692
  parents:
  - f83cbf7d-ee33-5b30-808f-74e1766f22aa
---
## What

Built the two things that close the update gap for adopted repos: **`hypergraph
upgrade`**, which refreshes an adopted repo's copies of what this package ships, and
**`hypergraph_version:`** in the config, which lets `check` say which half is behind.

The gap, stated plainly: three different things reach an adopted repo and they update
by three different mechanisms. The CLI lives outside the repo and `uv tool upgrade`
handles it. The node files are never touched by an upgrade. But the skills, the
sentinel AGENTS.md block and the CI workflows are **copies inside the repo**, and
nothing could see them go stale. That is not hypothetical: 0.0.6 fixed the adopt
workflow's step order, and every repo that had already run `skills install` kept the
installed skill describing the order 0.0.6 fixed, with nothing anywhere to say so.

## Why

Operator asked, after asking how updates propagate at all. The question exposed that
the answer was "you remember to tell people" — the adopter's copies carry no version,
so neither side could detect skew. Two prior burns point the same way: the shipped CI
template called `check --since` before that flag existed, so a copied artifact needed
a newer CLI than the adopter had [rec: long-peak-1620]; and the 0.0.5 HWM change
needed a migration nobody could have known to run without `check` naming it.

## Method

Measured first, because both compatibility questions are empirical:

- **An old CLI reads a new graph.** Ran the published 0.0.5 CLI's `check` against
  this repo's graph, written by 0.0.6: 0 violations, 0 warnings. Node files are
  markdown + frontmatter and every change so far has been additive, so the format is
  not what goes stale.
- **Re-running `skills install` upgrades in place.** Installed the 0.0.5 skills, ran
  the 0.0.6 installer over the top without deleting: the adopt skill went from the old
  wording to 8 steps with the interview. But `copytree(dirs_exist_ok=True)` *merges*,
  so a file removed upstream lingers forever — which `upgrade` fixes by replacing the
  tree wholesale.

`hypergraph upgrade [--repo] [--config] [--user] [--workflows] [--dry-run]`, with one
contract: **refresh what is already there, never install what is not.** An upgrade
that quietly adds CI to a repo that never wanted it is a worse failure than a stale
file, and the same rule is what keeps the command from writing outside the repo it was
pointed at. Consequences:

- skills: replaced wholesale (prunes removals), scope mirrors `skills install` —
  project by default, `--user` for `~/.claude/skills`. An implicit both-scopes pass was
  the first design and was wrong: a repo-scoped command must not edit `$HOME` unasked.
- AGENTS.md block: replaced between the sentinels in any of `AGENTS.md`, `CLAUDE.md`,
  `.hypergraph/AGENTS.md` that carries them; prose outside survives verbatim. Writing
  through a `CLAUDE.md → AGENTS.md` symlink edits the target and keeps the link, and
  the two paths dedupe to one write — adopt has warned about that rule in prose since
  it shipped, and here it falls out of the implementation.
- workflows: **reported, not overwritten**, unless `--workflows`. These are the one
  copied artifact adopters genuinely edit (different base branch, extra steps), and
  clobbering them by default would make `upgrade` unrunnable without reading a diff.
- refuses to run in this checkout: here `.claude/skills/*` are the dogfooding symlinks
  into `skills/` and the publish workflow deliberately differs from the template, so
  refreshing either from the package would overwrite the source with a copy of itself.

`hypergraph_version:` is stamped by `adopt --init`, by `upgrade`, and by the config
template hypergraph-init copies from. `check_version_skew` compares it to
`__version__`: older → "the copies are stale, run `hypergraph upgrade`"; newer → "the
CLI is the old half, run `uv tool upgrade`"; unparseable → silent, because a
pre-release string has no ordering; **absent → info, not warning**, since every repo
adopted before the stamp lacks one and that is normal. Always a warning at worst —
`check` exits nonzero only on violations, and failing someone's CI because their skill
files are a release behind would be hostile.

## Result

307 tests pass (15 new in `tests/test_upgrade.py`, plus two version-parity guards).

Rehearsed the actual situation end-to-end on a repo adopted earlier with the published
0.0.6 CLI: `check` printed the missing-stamp info → `upgrade` refreshed five skills and
stamped the config → `check` went quiet. Also verified: `--dry-run` writes nothing; a
second run reports "already current"; a stray file inside an installed skill is pruned;
a drifted workflow is reported and left alone until `--workflows`; a `CLAUDE.md`
symlink survives; a file with no sentinel block is not touched; and `upgrade` refuses
in this repo.

Two parity tests were added for the stamp itself, because the version now lives in
five places (pyproject, `__version__`, SPEC.md's header, this repo's config, the config
template). The SPEC one already caught a real drift during the 0.0.6 release; these two
close the same hole for the new sites.

Unreleased: this lands in the tree at 0.0.6. An adopter cannot run `hypergraph upgrade`
until a release carries it — which is the gap it exists to close, so it argues for
0.0.7 rather than sitting.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 24747568eadcddaa2403bdcff21966867c8b3c65

## State Impact

- target: NEW upgrade-path — how a release actually reaches an adopted repo: the CLI via uv, the copies via hypergraph upgrade, the node files not at all; skew detected by a config stamp rather than remembered. Status working, unreleased
- target: morning-crane-7863 — adopted repos are no longer write-once: the skills and AGENTS.md block an adoption installs can be refreshed in place, and check reports when they are behind
