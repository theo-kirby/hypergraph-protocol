---
node_id: ac530834-dc87-5fcc-a4ae-822ecc486ae6
slug: placid-ridge-4035
title: 'v0.0.5: the protocol becomes merge-safe — ancestry frontier, conflict markers, publish guards, CI'
created_at: '2026-08-09T12:26:31+00:00'
parents:
- vast-rain-4873
summary: Builds the five items from vast-rain-4873. I5 becomes an ancestry frontier with a migration aid; check rejects conflict markers at both check and authoring time; push gains a publish-branch gate and a not-the-owner stand-down; SPEC gains Collaboration; check --since plus two Actions templates. 282 tests, up from 250.
flywheel:
  node_id: d1338969-8407-52f7-bc2f-c71cc5df0eaf
  slug: ancient-term-2567
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: df2323c2ad62301cf7aee98e9bbf93fc09cec6aa4615d76d5826d651eb2c9b23
  parents_sha256: daf11f6ede389ae59ec6f4e0f0815d5631a3e230be0f85c4fd4328376244aa25
  parents:
  - 33be9687-071a-5ef3-baf8-dec744dc7c51
---
## What

v0.0.5 — the five items scoped in [rec: vast-rain-4873], built in the order that made
each next one safe: fix what is losing work, stop what corrupts, guard what publishes,
then state the doctrine and enforce it in CI.

1. **I5 is an ancestry frontier.** `high_water_mark:` takes one or more record tips;
   reconciled means *ancestor of some tip*. New `hypergraph hwm` / `hwm --suggest`.
2. **`check` rejects git conflict markers**, at check time and at authoring time.
3. **`push` guards.** A publish-branch gate, and a stand-down at exit 0 when the
   credentials are not the mirror's owner. `--allow-any-branch`, `--require-mirror`.
4. **SPEC gains a Collaboration section**, I5 is restated, and the skills carry the rule.
5. **`check --since <ref>`** plus two GitHub Actions templates, one installed here.

## Why

Every workflow the protocol had been proven under was one writer on one machine. The
three defects reproduced in vast-rain-4873 all fire on the *first* merge of concurrent
work, and all three are silent — the checker reported `0 violations` in every case.

The HWM one is the reason this was urgent rather than planned: it does not fail, it
**forgets**. A record node authored before the last reconcile and merged after it was
counted as already folded, dropped from the frontier permanently, with nothing anywhere
saying so. That is the one failure mode the whole protocol exists to prevent.

The doctrine half is cheap because the invariants already implied it. The record graph
is append-only with one file per node; the state graph is single-writer by I3. That is
the same line git merges on, so **contributors record and the maintainer reconciles**
did not need inventing, only stating.

## Method

**Ancestry frontier.** `read_hwm` returns a list (one slug, a comma-separated list, or
`none` → `[]`); `ancestors_of` walks parents; `unreconciled_nodes` is set subtraction.
`check_hwm` reports every unresolvable tip by name rather than the first.

The migration was the design problem, not the algorithm. Switching rules makes a
pre-0.0.5 graph surface side branches that *were* folded, which reads as "your work
vanished" and invites folding them twice. So `check` distinguishes them: unreconciled
nodes that predate the newest mark get a named hint pointing at `hwm --suggest`, which
prints the maximal tips covering what the timestamp rule had covered. Info, never a
violation — this is not new work, and it must not fail anyone's CI.

The viz consumes the same data. Its timeline draws one vertical rule and shades
everything right of it as unreconciled, which is only true of a linear graph, so the
exporter now sends `high_water_mark: null` whenever the frontier has more than one tip
and the per-node accent carries it instead. Changes went into `tools/viz/js/*` and
through `bundle_viz.py`, never into the generated region.

**Conflict markers.** `<<<<<<<`, `>>>>>>>` and diff3's `|||||||` are unambiguous at line
start. A bare `=======` is *not* — it is also a setext H1 underline — so it is only
reported inside a node that already shows a real marker. Wired into `run_check` for both
graphs and into `validate_node_content`, so the machine that would have committed it
refuses first.

**Push guards.** `publish_branch_block` compares HEAD against `publish_branch:`, else
`origin/HEAD`, else `main`; outside a git checkout it allows, because the node files are
the graph and git is how they usually travel, not a requirement. `mirror_not_ours`
compares the authenticated account against `mirror_account_id:`.

Both feed one `stand_down()` helper: print a line, exit 0, unless `--require-mirror`.
That keeps reconcile's publish step unconditional prose on a maintainer's main, on a
feature branch, and on a fork alike — the same property that made the mirror invisible
in the first place [rec: silver-ember-3035], now extended to *who* is running it.

**Deliberately not built: a dirty-tree guard**, despite being in the original sketch.
Reconcile publishes *before* it commits, on purpose, so `push`'s frontmatter writes land
in the same `git add`. A dirty graph is therefore the expected state at push time, and
refusing on it would break the documented flow.

**`check --since`.** Three-dot range: `<ref>...HEAD` is what the branch adds. Changes to
the graph dir, STATE.md and the cache are excluded, so a reconcile-only branch is not
asked to record itself. A missing ref names shallow clones, because that is what CI gets
by default and the error would otherwise read as "the branch is wrong".

## Result

**282 tests pass** (was 250), 32 of them new in `tests/test_collaboration.py`, including
the literal reproduction from vast-rain-4873: Bob at 09:30 on a branch, Alice at 10:00 on
main, and the assertion that Bob is reported unreconciled.

Verified on this repo, which turned out to be the ideal test case: **it already has a
two-tip record DAG** from the hg-viz merge. Nine nodes sit on `wise-river-3571` and are
not ancestors of the mark. They were folded correctly at the time, purely because the
reconcile ordering happened to be favourable. Under the new rule `check` surfaces all
nine, the migration hint fires, and `hwm --suggest` prints
`wise-river-3571, vast-rain-4873` — the exact frontier, adopted in this pass.

Live behaviour confirmed end to end: on main as the owner, `push --dry-run` runs
normally; on a feature branch it stands down at exit 0 and fails at exit 2 under
`--require-mirror`; with a deliberately wrong `mirror_account_id` it names both accounts
and stands down. `check --since main` against a real code-only commit produced the
violation naming `tools/hypergraph.py`.

Two existing tests changed contract rather than breaking: `read_hwm` returns `[]` for
`none`, and the no-transport degradation test now asserts exit 0 with the remedy still
in the message, plus exit 2 under `--require-mirror`.

Version 0.0.5 across `pyproject.toml`, `__version__` and the SPEC header. The standing
acceptance grep over the five SKILL.md bodies still returns zero hits, all markdown
links resolve, and no symlink dangles.

**Not done, and both are the Operator's call**: 0.0.5 is not released to PyPI (arm C
pins the version from pyproject, so a release mid-benchmark makes arms non-comparable
[rec: staid-field-2723]), and the publish workflow is shipped as a template but *not*
installed in this repo, because the mirror is still published from the maintainer's
machine and a publish job with no `FLYWHEEL_API_KEY` secret would fail on every merge.
The PR check workflow *is* installed, running the CLI from the checkout rather than PyPI
so it tests the version under test.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: dcfd50b703f8c2137d86269baf3772e50ff6ed34

## State Impact

- target: gilded-vale-8087 — the gap closes: all five items shipped and verified, including on this repo-s own two-tip record DAG. What remains open is narrower and named.
- target: young-wave-9364 — SPEC v0.0.5: I5 restated as an ancestry frontier, a new Collaboration section, the repo-fork vs graph-fork disambiguation, and the HWM vocabulary entry.
- target: wandering-sun-8831 — Both reproduced defects fixed: ancestry-based unreconciled enumeration with a migration hint, and conflict-marker rejection. New hwm verb and check --since. 282 tests.
- target: empty-forest-6305 — push gains a publish-branch gate and a stand-down at exit 0 when credentials do not own the mirror; --allow-any-branch and --require-mirror. No dirty-tree guard, deliberately.
- target: dry-wildflower-2260 — reconcile gains the maintainer-on-main rule, frontier guidance for the HWM step, and a post-merge sync guardrail; record states that recording is safe on any branch.
