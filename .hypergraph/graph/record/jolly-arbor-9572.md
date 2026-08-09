---
node_id: 77eba77d-1430-5be5-929a-28e6e0e3875f
slug: jolly-arbor-9572
title: 'P0: the repo dogfoods its own skills, and `skills install` can no longer destroy them'
created_at: '2026-08-09T11:01:57+00:00'
parents:
- cold-mountain-5872
summary: ''
---
## What

Phase 0 of the plan in [rec: cold-mountain-5872], landed independently of the rest:
this repo now dogfoods its own skills, `hypergraph skills install` can no longer
destroy them, and AGENTS.md stopped asserting something false.

Four changes:

1. **Five committed relative symlinks** `.claude/skills/hypergraph-* →
   ../../skills/<name>`.
2. **`cmd_skills` refuses to clobber a link into its own source** — exit 2, was silent
   data loss.
3. **`skills install --link`**, with `install.sh` reduced to a wrapper around it.
4. **AGENTS.md corrected**, plus a `## The CLI` preamble in all five skills.

## Why

Direct consequence of the decision node's second problem: the skills were not
installed. `~/.claude/skills/` held only the eight `flywheel-*` skills, and this repo
had no `.claude/` directory, so `/hypergraph-record` was an unknown slash command in
the repo that ships it. AGENTS.md documented this as intended ("They are not installed
by default") rather than as the gap it was.

Project scope, not `--user`. A global install puts `hypergraph-*` beside `flywheel-*`
in **every** session the user has, everywhere, including repos that have never heard of
the protocol. Symlinks rather than copies because git stores symlinks natively, they
survive clone, and editing `skills/<name>/SKILL.md` edits the live skill — the only
arrangement that cannot go stale.

Committing those symlinks is what made an existing latent bug reachable, which is why
the fix belongs in this phase and not a later one.

## Method

**The bug.** `cmd_skills` did `if dst.is_symlink(): dst.unlink()` followed by
`shutil.copytree(...)`. With `.claude/skills/*` now symlinked into `skills/`, a
contributor running the documented `hypergraph skills install` inside this checkout
would have unlinked each dogfooding symlink and written a **copy of the skill over its
own link** — the live skill replaced by a frozen snapshot of itself, with no error and
no output distinguishing it from a normal install. Subsequent edits to `skills/` would
then silently stop taking effect.

Fix: a `_links_into(dst, tree)` helper resolves the destination and tests whether it
lands inside the source tree; if so, `install` raises rather than writes. A symlink
pointing *elsewhere* is still replaced wholesale, which is the pre-existing behaviour
and correct. Broken or looping links resolve with `OSError` and are treated as "not
ours", so they get replaced rather than crashing the install.

**`--link`.** Symlinks instead of copies. Only safe where the source tree stays put, so
it is a flag and not the default: an installed wheel must hand out self-contained
copies, which is why `copytree` materializes the symlinked `references/` entries.
`install.sh` is now four lines of wrapper over `skills install --link --target`, so
there is one implementation of "install the skills" instead of two that could drift.

**`[tool.uv] package = false` left alone**, deliberately. Flipping it would build a
wheel on every `uv run` and collide with the `force-include` allow-list that
`tests/test_packaging.py` guards. The dev/adopter split is documented instead: a
two-line `## The CLI` preamble in each skill, and the same statement once in AGENTS.md.

**Verification.** `uv run tools/hypergraph.py skills install` in this repo → exit 2,
"already linked to the source". `--target DIR` still copies (exit 0). `install.sh`
against a scratch dir produces five symlinks. Full suite: 198 passed.

## Result

Working, with three new tests. `test_skills_install_refuses_to_clobber_a_link_to_the_
source` asserts exit 2 *and* that the destination is still a symlink afterwards — the
second assertion is the one that would have caught the original bug, since the old code
also "succeeded". `test_skills_install_link_edits_through` asserts the link resolves to
the source and that a following plain `install` is then refused.

Confirmed live: the five symlinks resolve, git stores them as mode-120000 blobs (1
insertion each, not a directory copy), and `.gitignore` needed a comment in the
existing "NOT ignored, deliberately" idiom because it already ignores
`/.claude/worktrees/` — without it the next person to read that file would reasonably
assume all of `/.claude/` was scratch.

**This phase only takes effect next session.** Claude Code loads skills at session
start, so `/hypergraph-orient` becomes a resolvable slash command on the next cold
start, not in the session that created the links. That is also the verification step:
edit a SKILL.md, restart, confirm the edit is live — which proves the symlink rather
than a copy is what the harness read.

One thing this does **not** fix: harnesses that do not read `.claude/skills` at all
(pi, for one). For those, reading `skills/<name>/SKILL.md` directly remains the only
path, and AGENTS.md now says so as a property of those harnesses rather than as a
property of this repo.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: cd456a2e69eb1c8b15b2b06bbd333dc1dbe47214

## State Impact

- target: bold-field-1268 — dogfooding gap closed: .claude/skills/hypergraph-* are five committed relative symlinks into skills/, so a fresh clone resolves /hypergraph-record and editing skills/<name>/SKILL.md edits the live skill. Takes effect next session — Claude Code loads skills at session start.
- target: dry-wildflower-2260 — skills install had a silent data-loss bug: it unlinked a symlinked destination and copied over it, so running the documented install inside this checkout would have replaced each dogfooding symlink with a stale snapshot of itself, with no error. Now exit 2 when the destination resolves inside the source tree. New: skills install --link; install.sh is a wrapper over it, so there is one implementation instead of two. All five skills gained a ## The CLI preamble stating uv run tools/hypergraph.py for a dev checkout vs bare hypergraph for adopters — [tool.uv] package = false means the bare form never resolves in this repo, so every skill line reading "hypergraph new record" was previously unexecutable here.
