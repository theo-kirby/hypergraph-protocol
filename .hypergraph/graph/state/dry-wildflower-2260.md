---
node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
slug: dry-wildflower-2260
title: Skills
created_at: '2026-08-06T21:41:21.141576+00:00'
parents:
- cool-king-8586
summary: Six single-path skills (init, adopt, record, reconcile, orient, dispatch), dogfooded through committed .claude/skills symlinks. Dispatch packages one aimed pass; the unattended series remains Autonomous operation's gap.
flywheel:
  node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
  slug: dry-wildflower-2260
  revision: 18
  pushed_at: '2026-08-18T12:12:46+00:00'
  content_sha256: a8996ba6917e6bbadbaa58629fcd76f7bfd529f1ec8c4bacf3076031dc312e0e
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

- **The skills**: `hypergraph-init` (roots, skeleton, config), `hypergraph-record` (causally-parented record nodes, always declaring State Impact, never writing state), `hypergraph-reconcile` (the single writer: folds impacts, advances the HWM, regenerates STATE.md, checks, publishes), `hypergraph-orient` (read-only frontier brief), `hypergraph-adopt` (the conversion path for repos with a past) and, since 0.0.11, `hypergraph-dispatch` (an agent aimed at a target — frontier slug, prose goal, or region — under a bounded budget, claiming its work through a `Dispatch:` decision node) [rec: spring-fog-0600] [rec: late-isle-6483] [rec: young-sage-8406]. The count is deliberately written down nowhere anymore — it rotted the moment the sixth landed [rec: gentle-journey-8382].
- **They are single-path.** Every backend-dispatch preamble, every hosted-store workflow branch and all five adapter symlinks are gone; the acceptance test chosen in advance holds, with a grep of the five bodies for `flywheel|lease|MCP|429|409` returning **zero hits** and no dangling symlink under `skills/`. An agent reading them learns one system [rec: calm-sand-3399]. The sixth keeps the same isolation: it may name the `hypergraph dispatch` verb, never a provider's internals, which stay behind backend/lanes.md exactly as the mirror stays behind the CLI [rec: young-sage-8406].
- **What each cut bought** [rec: calm-sand-3399]: orient lost two workflows plus a no-store fallback and got *no* fallback, because there is no degraded mode — the repo **is** the graph; record lost the rate limits, because pacing is the tool's job rather than something an agent recites; reconcile gained a single unconditional `hypergraph push` step with the two nonzero-exit meanings named, because an append-only breach and drift are genuinely different failures; init stopped asking a storage question that no longer exists. Reconcile's step 8 went from 23 lines of choreography to 9, and its steps were reordered so **publish precedes commit**, which puts `push`'s frontmatter writes inside the same `git add`.
- **This repo dogfoods them.** `.claude/skills/hypergraph-*` are committed relative symlinks into `skills/`, so a fresh clone resolves `/hypergraph-record` and editing `skills/<name>/SKILL.md` edits the live skill — the only arrangement that cannot go stale. Project scope, not `--user`: a global install would put these into every session the user has, everywhere [rec: jolly-arbor-9572]. Every skill carries a two-line `## The CLI` preamble, because `[tool.uv] package = false` means the bare `hypergraph` form never resolves here, so every skill line was previously unexecutable *in the repo that ships it*.
- **Onboarding outside the skills channel**: AGENTS.md states the record discipline as non-negotiable for arriving agents, with CLAUDE.md containing only `@AGENTS.md`. Added after blind test #1 and validated by blind test #2, a controlled retest with AGENTS.md as the only changed variable [rec: tiny-sunset-0847] [rec: little-bar-4131].
- **The collaboration rules are split across two skills, which is the point** [rec: placid-ridge-4035]: reconcile carries the maintainer-on-main rule, frontier guidance in its HWM step, and a guardrail to start from `sync` rather than a bare `check` after a merge; record carries the converse a contributor needs — recording is safe on any branch, fork or machine, and it is the *whole* obligation.
- **record teaches tagging, and the guidance is mostly about restraint** [rec: clear-moss-4527]: read `tags.yml`, use declared names only, add one with `hypergraph tags add` and never by hand, and in a repo with no `tags.yml` **tag nothing**. The load-bearing sentence is that a tag is a way to *find* nodes and not a way to assert things about them.
- **record's step 7 stopped being one line, because it decides whether the artifact feature reaches the field at all** [rec: shady-bay-7654]. It said "commit the files and reference them by path"; it now says three things and names the third as the one that is easy to skip: commit them *or don't* (gitignoring a 40 GB dataset is a legitimate call, but an uncommitted file that gets published is one the mirror alone holds), **explain** them in `## Method`/`## Result` because prose is the claim, and **enumerate** them because the list is the claim's index and no tool reads prose.
- **The 0.1.0 audit measured skill/spec drift, queued for the gate's later units** [rec: lively-spring-9646]: the reconcile skill still states unreconciled enumeration by wall clock — the pre-0.0.5 rule I5 exists to forbid — in the one skill that must get I5 right; the dispatch skill teaches open/ls/harvest but never `close`, while naming the abandoned-lane failure it remedies; three documents give three different counts of who passes `--reconcile` (the true answer is three: init and adopt once each at setup, reconcile ongoing); and adopt shipped three representations of one procedure plus a factual `--slug` error at 43% of all skill bytes — **the adopt half is fixed**: one mode-branched workflow whose Mode A order is native (pull → import → `--init`), the corrective note and the duplicate walkthrough deleted (363 → 286 lines), with the interview and the four authoring traps kept verbatim [rec: mellow-birch-2818].
- **The unattended-loop gap narrowed at 0.0.11**: `hypergraph-dispatch` packages one aimed pass — orient, claim, work, record, close — proven by two acceptance runs whose second read the first's claim and steered around it [rec: young-sage-8406] [rec: idle-crow-3832] [rec: bold-sand-5009]. What no skill packages yet is the *series* — resume, again and again, across contexts — which Autonomous operation holds [rec: late-sage-5549].

## Negative knowledge

- [scope: protocol discoverability by uninstructed agents | confidence: high | evidence: tiny-sunset-0847, little-bar-4131] README/SPEC presence and installed skills do not by themselves cause a protocol-naive agent to record its work — it can use the graphs as app data without recognizing the obligation; repo-level agent onboarding (AGENTS.md/CLAUDE.md) is required, and the controlled retest confirms it is also sufficient.
- [scope: documenting where a tool's skills live | confidence: high | evidence: sweet-wave-7885, jolly-arbor-9572] a README claim that something is installed is not an install. `AGENTS.md` asserted the skills were in `~/.claude/skills`; they were in the repo and nowhere else, and the resulting "unknown skill" errors were read as a harness bug for a whole session. Documentation that states a machine's state, rather than the command that produces it, goes stale silently. The durable fix was not better wording but committed symlinks — a fact in the repo instead of a claim about a machine.
- [scope: installers that write over their own source | confidence: high | evidence: jolly-arbor-9572] `skills install` unlinked a symlinked destination and copied over it, so running the documented command inside this checkout would have replaced each dogfooding symlink with a stale snapshot of itself — no error, and output indistinguishable from a normal install. Any installer whose destination can legitimately be a link **into its own source** must detect that case and refuse, because the failure is invisible at the moment it happens and only surfaces later as edits that mysteriously stop taking effect.
- [scope: skills as a delivery channel | confidence: high | evidence: jolly-arbor-9572, calm-sand-3399] a skill edit is live only from the *next* session, because skills load at session start — so a rewritten skill has not been tested by the act of rewriting it, and the run that proves it is always a later one.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-fog-0600 — four skills and the installer landed (M4)
- steep-cell-5173 — orient validated cold-start
- patient-limit-9007 — directive-decision-node guidance added to record
- tiny-sunset-0847 — AGENTS.md onboarding added after blind test #1
- little-bar-4131 — blind test #2 validated AGENTS.md
- late-isle-6483 — the fifth skill, hypergraph-adopt, plus the agents-block template
- stormy-dew-2969 — mode-B marker parentage corrected from field use
- tender-moss-3792 — adopt/reconcile/init updated for fork-import
- sweet-wave-7885 — skills are not installed by default; AGENTS.md corrected
- jolly-arbor-9572 — dogfooding symlinks committed; the install-over-source bug fixed
- calm-sand-3399 — the five skills go single-path; the acceptance grep returns zero hits
- placid-ridge-4035 — reconcile gains the maintainer-on-main rule; record covers contributors
- clear-moss-4527 — record gains a tagging step built around restraint
- shady-bay-7654 — record's step 7 rewritten around enumerating evidence
- late-sage-5549 — the missing unattended-loop skill named as a gap rather than left unstated
- young-sage-8406 — the sixth skill: hypergraph-dispatch
- gentle-journey-8382 — skill-count phrasing goes count-free across the docs
- vast-birch-5192 — Operator directive: the release label is 0.0.11, not 0.9.0
- lively-spring-9646 — the 0.1.0 audit: skill drift measured against SPEC, fixes queued
- mellow-birch-2818 — U7: adopt collapsed to one procedure with the native Mode A order
