---
node_id: 8ba48515-54cb-55c3-b94d-48c1bcd46ae8
slug: young-sage-8406
title: 'The sixth skill: hypergraph-dispatch, an agent aimed at a target'
created_at: '2026-08-16T17:58:51+00:00'
parents:
- windy-eagle-6074
summary: ''
flywheel:
  node_id: 4245ba73-15e8-5ae2-b7f9-90d22caac299
  slug: nameless-dawn-4584
  revision: 0
  pushed_at: '2026-08-16T18:24:57+00:00'
  content_sha256: 21d7b2d79b074d257ba3666474eb27d3c9625b152e4754f72d48aad59e728ce3
  parents_sha256: be5451e0e07de515263bb6b8dae87066687622251e8fc65244359103fe443780
  parents:
  - d2ad35be-88ce-5f38-a80e-0da9d37d27ed
---
## What

The sixth skill: `skills/hypergraph-dispatch/SKILL.md` — dispatch an agent *at*
a target and let it work a bounded budget in its own lane. Ships with
`references/` symlinks (spec.md, local-adapter.md, lanes.md) and the committed
`.claude/skills/hypergraph-dispatch` dogfooding symlink. No packaging change:
`skills install` and `upgrade` discover by glob, and both now pick up all six
(verified against a scratch target; the symlinked references materialize as
real files on copy, so the installed skill is self-contained).

## Why

`hollow-rain-8997` names the gap: five skills that each do one thing, and no
loop that composes them toward a goal. Dispatch is that loop, written as a
skill because the composition is judgment (pick a gap, read claims, know when
to stand down) — the CLI only carries the lane mechanics.

## Method

hypergraph-record's skeleton, with the new content in four blocks. **Target
grammar**: a frontier state slug ("work this node"); a prose goal (record the
Operator-directive decision node first per SPEC Forward work — that node *is*
the dispatch node, and its impact carries the `NEW`/delta declaration); or a
region (`within <state-slug>`: orient over the subtree, pick the best
open/broken/blocked descendant, say why). Budget: N units or a stated stopping
rule, default 1. **Claim convention**: the dispatch decision node is written
first, titled `Dispatch: <target>`, impact `none: lane claim — …`, causally
parented on a provenance slug of the target; work nodes are its children with
real impacts; closure is a `Dispatch closed: <n> unit(s) …` line in the final
child's `## Result`; a live claim is an unreconciled `Dispatch:` node with no
closure descendant. **Claim avoidance** (advisory): read `hypergraph hwm`
outstanding + grep for `Dispatch:` titles + `hypergraph dispatch ls`; if
claimed, pick elsewhere and name the avoided claim in `## Why`; worst case is
duplicated work, never corruption. **Guardrails**: never reconcile/write state;
budget exhausted mid-unit → record the partial unit honestly and stop;
re-dispatch is a new node, never an edit; no chaining dispatches to dodge the
budget; stand down at exit 0 over guessing, writing nothing. The skill may
name the `hypergraph dispatch` CLI verb but never a provider's internals —
mirror-style isolation.

## Result

Skill committed and discoverable: `skills install --target <scratch>` lists six
skills, dispatch included, references materialized. Suite unchanged: 293
passed, 2 skipped. The skill loads at session start, so it is exercisable from
the *next* session — the acceptance runs are planned as fresh sessions for
exactly this reason.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: d198908691eb4ad55c4c5a4c95293ab1f24bbdd9

## State Impact

- target: dry-wildflower-2260 — a sixth skill exists: hypergraph-dispatch (target grammar: frontier slug | prose goal | region; budget-bounded; advisory lane claims via Dispatch: decision nodes; closure lines); the skill count in this node's claim is now six and should go count-free
- target: hollow-rain-8997 — 'no loop that composes them' is falsified in code-and-skill form: the dispatch skill is the loop (orient → claim → work → record → close); whether it carries work across a series of contexts remains the open question
