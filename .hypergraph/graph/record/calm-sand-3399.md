---
node_id: af331184-d268-5768-95d2-658e1ab3c28e
slug: calm-sand-3399
title: 'P3-P5: the skills go single-path, config drops the backend menu, adoption gets computed facts'
created_at: '2026-08-09T11:37:57+00:00'
parents:
- silver-ember-3035
summary: ''
flywheel:
  node_id: 7e8e6ea3-b284-5ccd-afe8-dce3eb9682e7
  slug: cool-flower-6765
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 832465e6693758261706171d4fa358996f730c66e097d8f5a4d71ab571c7159c
  parents_sha256: 44e8772a1f086735e9e06bf096b9c9c8410aff7a4f1643373d7bf1502450d911
  parents:
  - 08bd075f-b511-5510-83eb-7add7298d19e
---
## What

Phases 3, 4 and 5 of [rec: cold-mountain-5872] — the part the whole change was for.

**P3.** Every skill lost its backend-dispatch preamble, its `flywheel` workflow branch,
and its `references/flywheel-adapter.md` symlink. `backend/flywheel-adapter.md` →
`backend/flywheel.md`, demoted to ~70 lines and banner-marked *"not an agent-facing
document"*.

**P4.** `templates/config.example.yml` dropped the `backend:` menu and gained
`mirror_account_id:`. `check` warns (never fails) on a legacy `backend:` key. Version
0.0.4 across pyproject, `__version__` and the SPEC header, with a packaging assertion
tying the last of those to the first.

**P5.** Four `hypergraph adopt` affordances — `--survey`, `--pull`, `--init`/`--marker`,
`--resolve-prefixes` — plus the adopt skill rewritten around them.

## Why

P1 and P2 made the mechanism removable. This is the removal, and the reason the whole
change was worth doing: **the agent now learns one system.** It runs local `hypergraph`
commands against local files, and nothing in its context describes a hosted store,
a lease, a rate budget, or an HTTP status code.

The measurable version of that goal, chosen in advance as the acceptance test: grepping
the five SKILL.md bodies for `flywheel|lease|MCP|429|409` returns **zero hits**. It does.

For P5, the motivation is a budget argument rather than a correctness one. Adoption is
the one workflow where an agent's judgment is the scarce resource — distilling honest
claims, mining negative knowledge, interviewing for invisible dead ends — and it was
spending that budget on `ls -la`, `readlink`, hand-written YAML and prefix arithmetic.

## Method

**P3, per skill.** orient 78 → 59: two workflows plus a no-MCP fallback collapse into
one workflow and no fallback at all — *there is no degraded mode, the repo **is** the
graph*. The "prefer frontier over `working`" advice was buried inside the flywheel
branch and is backend-agnostic, so it was salvaged into the surviving workflow rather
than deleted with its host. Staleness became a git question.

record 88 → 77: evidence is commit-the-files-and-reference-by-path; the write limits
are gone, because pacing is the Pacer's job now, not something an agent recites.

reconcile 117 → 94, and **step 8's 23 lines of choreography became 9**. Publishing is
`hypergraph push`, unconditional, with the two nonzero-exit meanings named because they
are genuinely different failures — an append-only breach is fixed locally, drift is
fixed by re-publishing — and the standing rule that local files are canonical. The
steps were reordered so publish comes *before* commit, which means `push`'s frontmatter
writes land in the same `git add` instead of dangling until the next one.

init 99 → 85: storage is no longer a question to ask the user, and a new When-To-Use
line routes repos-with-a-past to adopt, because init writes a day-one frontier and on a
mature codebase that is a fiction.

adopt 128 → 150 (it grew, deliberately — see P5): step 1 is `hypergraph mirror pull`,
step 5's 20-line mirror sub-protocol is gone, and the guardrail downgraded from "stop
and ask for MCP" to "authenticate; `mirror doctor` says what is wrong".

The five symlink deletions and the `git mv` are **one commit**, so no revision in
history has dangling references.

**P4.** The breaking change is that a missing `backend:` key used to mean `flywheel`
and now means the node files — correct by construction, since there is exactly one
thing it can mean. `check` warns on any value that is not `local` and names the
re-homing migration in `backend/mirror.md`. Warning, never violation: failing
someone's CI over a key the tool no longer reads would be hostile, and re-homing is not
a five-second fix.

The SPEC header said v0.0.2 while the tool shipped 0.0.3 — the document describing the
protocol disagreeing with the artifact implementing it. Four lines of assertion closes
that permanently.

**P5.** Each affordance replaces a specific manual mechanic:

- `--survey` — git shape (first commit, contributors, commit clusters as candidate
  eras, highest-churn paths), source dirs, doc inventory, test framework, and
  **AGENTS.md/CLAUDE.md presence plus symlink status**. That last one was `ls -la` and
  `readlink` by hand, guarding a rule the skill states in prose (never break a
  `CLAUDE.md → AGENTS.md` symlink); it is now mechanical.
- `--pull` — the same as `mirror pull`, which is what removes MCP from mode A entirely.
- `--init` / `--marker` — mints both roots and writes a *valid* config; validates that
  the marker slug resolves before recording the epoch.
- `--resolve-prefixes` — maps `[0-9a-f]{8,}` prefixes cited in tracked docs to slugs,
  **reporting ambiguity rather than guessing**, and listing hex tokens that match no
  node separately rather than dropping them silently.

The **interview** stayed in the skill and became an explicit numbered list of five
questions, each routed to where its answer lands: what didn't work and what in the docs
is now false become negative knowledge and `broken` statuses; what is externally
blocked becomes `blocked`; what you are deliberately not doing becomes a decision
record node, not a state claim.

## Result

**Acceptance test passes**: `grep -iE "flywheel|lease|MCP|429|409" skills/*/SKILL.md`
→ zero hits. `find skills -type l ! -exec test -e {} \; -print` → empty. All markdown
links across SPEC/README/backend/skills resolve.

250 tests pass (`-m "not live"`); `check` on this repo is 0 violations, 0 warnings;
`test_viz_bundle_in_sync` still passes, which proves nothing landed in the generated
region of `tools/hypergraph.py`. `hypergraph --version` reports 0.0.4 consistently
across module, pyproject and the SPEC header.

**P5 verified on a scratch repo with real git history**: `--init` produced a graph that
checks **0/0**; `--marker` refused `absent-node-9999` with an error naming the
consequence (an unresolvable marker exempts nothing, silently, and then every legacy
node fails I2 instead of being legacy) and accepted a real slug; a second `--marker`
call refused to append a rival `epoch:` block. `--resolve-prefixes` against this repo's
own export mapped **all 53** node-id prefixes cited in its docs with **0 ambiguous**,
and correctly set aside 1057 hex tokens that match no node — almost all git SHAs.

**Deliberately not built: CLI-generated prose.** No prehistory bodies, no `## Current`
claims, no negative-knowledge entries. It would produce exactly the aspirational
template-filling adopt's guardrails forbid, and it breaks I8 by definition: a claim
nobody derived from evidence they read is not re-derivable. The skill now carries that
as a guardrail in as many words — *the CLI computes facts; the agent writes claims*.

**Two things this change does not do**, both known and both deliberate:

- **P0 and P3 only take full effect next session.** Claude Code loads skills at session
  start, so the rewritten SKILL.md bodies and the `.claude/skills` symlinks become live
  on the next cold start. The single-path skills have not yet been *run* by an agent
  that read them as skills.
- **0.0.4 is not released to PyPI.** Arm C pins the version from pyproject and treats
  relaunches as cold starts against the exact installed artifact, so a bump between
  benchmark runs makes arms non-comparable [rec: staid-field-2723]. Sequencing that
  release against the benchmark stays an Operator call.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 54e17b3850ab32b0d0f0e5313f03dd95e73f85ca

## State Impact

- target: dry-wildflower-2260 — the objective landed and is mechanically verified: grepping the five SKILL.md bodies for flywheel|lease|MCP|429|409 returns zero hits, and no references/flywheel-adapter.md symlink remains. orient 78->59 (two workflows plus a no-MCP fallback collapse to one workflow and no fallback), record 88->77, reconcile 117->94 with step 8 going from 23 lines of choreography to 9, init 99->85, adopt rewritten around the new affordances. reconcile also reordered so publish precedes commit, which puts push frontmatter writes in the same git add. The skills load at session start, so these bodies become live next session and have not yet been run by an agent that read them as skills.
- target: blue-sun-8921 — backend/flywheel-adapter.md is now backend/flywheel.md, ~70 lines, banner-marked "not an agent-facing document", keeping only what the push code needs: the six repo_context keys, local_temp_node_id, base_committed_revision semantics, the 409/429 contract, write limits, and add-parent-before-remove ordering. The rename and the five symlink deletions are one commit, so no revision has dangling references.
- target: young-wave-9364 — version is 0.0.4 across pyproject, __version__ and the SPEC header. Those had drifted: the spec said v0.0.2 while the tool shipped 0.0.3, so the document describing the protocol disagreed with the artifact implementing it. A fourth packaging assertion ties the SPEC header to pyproject and closes it permanently.
- target: empty-forest-6305 — config schema migrated: templates/config.example.yml drops the backend: menu and gains mirror_account_id:. Breaking change handled as a warning — a missing backend: key used to mean flywheel and now means the node files, correct by construction since there is one thing it can mean. check warns on any backend: that is not local and names the re-homing migration in backend/mirror.md, but never fails: failing someone CI over a key the tool ignores would be hostile.
- target: morning-crane-7863 — four adopt affordances shipped: --survey (git shape, candidate eras, churn, docs, tests, and AGENTS.md/CLAUDE.md symlink status, replacing roughly fifteen exploratory bash calls), --pull (removes MCP from mode A entirely), --init/--marker (mints roots and writes a valid config; refuses a marker slug that does not resolve, because an unresolvable marker exempts nothing silently), and --resolve-prefixes (maps cited node-id prefixes to slugs, reporting ambiguity rather than guessing). Verified on a scratch repo: --init checks 0/0, --marker refuses a bogus slug and refuses a second epoch block, --resolve-prefixes mapped all 53 of this repo own ids with 0 ambiguous. The interview became an explicit five-question list, each answer routed to where it lands. New negative knowledge, general in scope and decided here: the CLI must never generate prose — no prehistory bodies, no ## Current claims, no negative-knowledge entries — because a claim nobody derived from evidence they read is not re-derivable, which breaks I8 by definition.
