---
node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
slug: dry-wildflower-2260
title: Skills
created_at: '2026-08-06T21:41:21.141576+00:00'
parents:
- cool-king-8586
summary: Five single-path skills (zero flywheel/lease/MCP/429/409 hits), dogfooded through committed .claude/skills symlinks; live from the next session start; working.
flywheel:
  node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
  slug: dry-wildflower-2260
  revision: 13
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 8bddc6cd3ffbd76e30380c774887d56354f0e0e7374fdb33fa99dc4b545c3c01
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

- Five skills: hypergraph-init (roots + skeleton + config), hypergraph-record (causally-parented record nodes, always declares State Impact, never writes state), hypergraph-reconcile (single writer: folds impacts, advances HWM, regenerates STATE.md, runs check, publishes), hypergraph-orient (read-only frontier brief), and hypergraph-adopt (conversion path for repos with a past) [rec: spring-fog-0600] [rec: late-isle-6483].
- **They are single-path.** Every backend-dispatch preamble, every `flywheel` workflow branch, and all five `references/flywheel-adapter.md` symlinks are gone. The acceptance test chosen in advance holds: grepping the five SKILL.md bodies for `flywheel|lease|MCP|429|409` returns **zero hits**, and no dangling symlink remains under `skills/` [rec: calm-sand-3399]. An agent reading them learns one system.
- Sizes after the rewrite: orient 78→59, record 88→77, reconcile 117→94, init 99→85, adopt 128→150 (adopt grew deliberately, around the new affordances). **Reconcile step 8 went from 23 lines of choreography to 9** [rec: calm-sand-3399].
- What each cut bought: orient lost two workflows plus a no-MCP fallback for one workflow and *no fallback* — there is no degraded mode, the repo **is** the graph; record lost the rate limits, because pacing is the tool's job rather than something an agent recites; reconcile gained a single unconditional `hypergraph push` step, with the two nonzero-exit meanings named because they are genuinely different failures (an append-only breach is fixed locally, drift is fixed by re-publishing); init stopped asking a storage question that no longer exists [rec: calm-sand-3399].
- Reconcile's steps were reordered so **publish precedes commit**, which puts `push`'s frontmatter writes inside the same `git add` rather than leaving them dangling until the next one [rec: calm-sand-3399].
- init gained a When-To-Use line routing repos-with-a-past to adopt: init writes a day-one frontier, and on a mature codebase that is a fiction [rec: calm-sand-3399].
- **This repo now dogfoods the skills.** `.claude/skills/hypergraph-*` are five committed relative symlinks into `skills/`, so a fresh clone resolves `/hypergraph-record` and editing `skills/<name>/SKILL.md` edits the live skill — the only arrangement that cannot go stale. Project scope, not `--user`: a global install would put `hypergraph-*` into every session the user has, everywhere [rec: jolly-arbor-9572].
- Every skill carries a two-line `## The CLI` preamble: `uv run tools/hypergraph.py …` in a dev checkout, bare `hypergraph` for an adopter. `[tool.uv] package = false` means the bare form never resolves in this repo, so every skill line reading `hypergraph new record …` was previously unexecutable *in the repo that ships it* [rec: jolly-arbor-9572].
- `hypergraph skills install` gained `--link`, and `install.sh` is now a wrapper around it, so there is one implementation of "install the skills" rather than two that could drift [rec: jolly-arbor-9572].
- hypergraph-adopt covers both modes — A: import an existing hosted graph verbatim as the fork with mandatory `archive:` config; B: author 1–3 prehistory nodes from the repo itself — plus the epoch marker, distillation into an honest state graph, the init tail, and onboarding install; `templates/agents-block.md` ships with it [rec: late-isle-6483] [rec: tender-moss-3792].
- Field correction from tbinn: the mode-B marker parents on the newest prehistory node, not `--root` — the CLI correctly refuses a second parentless root per graph [rec: stormy-dew-2969].
- Onboarding outside the skills channel: AGENTS.md states the record discipline as non-negotiable for arriving agents, with CLAUDE.md containing only `@AGENTS.md`; added after blind test #1 (machinery used, obligation missed) and validated by blind test #2, a controlled retest with AGENTS.md as the only changed variable [rec: tiny-sunset-0847] [rec: little-bar-4131].
- Open: the rewritten skills **have not yet been run by an agent that read them as skills**. Claude Code loads skills at session start, so both the dogfooding symlinks and the single-path bodies become live on the next cold start [rec: jolly-arbor-9572] [rec: calm-sand-3399].
- reconcile gained the maintainer-on-main rule in its When-To-Use, frontier guidance in the HWM step (usually one slug, several after a merge, and what to do when `check` names `hwm --suggest`), and a guardrail to start from `sync` rather than a bare `check` after a merge. Its publish step now names all three stand-down cases in one sentence instead of one [rec: placid-ridge-4035].
- record gained the converse, which is what a contributor needs: recording is safe on any branch, fork or machine, because record nodes are one file each and merge without conflict — and it is the *whole* obligation, because the maintainer reconciles after the merge [rec: placid-ridge-4035].
- **record now teaches tagging, and the guidance is mostly about restraint** [rec: clear-moss-4527]: read `.hypergraph/tags.yml`, use declared names only, add one with `hypergraph tags add` and never by hand, and in a repo with no `tags.yml` **tag nothing**. The load-bearing sentence is that a tag is a way to *find* nodes and not a way to assert things about them — no invariant reads one, so a claim living only as a tag is invisible to `check` and to reconcile. adopt's step 5 gains what travels and what does not, and its step 6 gains the pointer-tag routing; two of its prose references to "tags" meaning *git* tags were renamed to stop the collision.

- **record's step 7 stopped being one line, because it is the step that decides whether the artifact feature reaches the field at all** [rec: shady-bay-7654]. It used to say "commit the files and reference them by path"; it now says three things, and names the third as the one that is easy to skip: commit them *or don't* (gitignoring a 40 GB dataset is a legitimate call, but an uncommitted file that gets published is one the mirror alone holds), **explain** them in `## Method`/`## Result` because prose is the claim, and **enumerate** them with `hypergraph artifacts add` or `--artifact` because the list is the claim's index and no tool reads prose. Never attach to a state node. The guardrail beside it names `artifacts:` as the one frontmatter key that may be edited on a committed record node — the append-only hash covers the *body* — while the body still may not be, and `hypergraph update` still refuses record nodes outright.

## Negative knowledge

- [scope: protocol discoverability by uninstructed agents | confidence: high | evidence: tiny-sunset-0847, little-bar-4131] README/SPEC presence and installed skills do not by themselves cause a protocol-naive agent to record its work — it can use the graphs as app data without recognizing the obligation; repo-level agent onboarding (AGENTS.md/CLAUDE.md) is required, and the controlled retest confirms it is also sufficient.
- [scope: documenting where a tool's skills live | confidence: high | evidence: sweet-wave-7885, jolly-arbor-9572] a README claim that something is installed is not an install. `AGENTS.md` asserted the skills were in `~/.claude/skills`; they were in the repo and nowhere else, and the resulting "unknown skill" errors were read as a harness bug for a whole session. Documentation that states a machine's state, rather than the command that produces it, goes stale silently. The durable fix was not better wording but committed symlinks — a fact in the repo instead of a claim about a machine.
- [scope: installers that write over their own source | confidence: high | evidence: jolly-arbor-9572] `skills install` unlinked a symlinked destination and copied over it, so running the documented command inside this checkout would have replaced each dogfooding symlink with a stale snapshot of itself — no error, and output indistinguishable from a normal install. Any installer whose destination can legitimately be a link **into its own source** must detect that case and refuse, because the failure is invisible at the moment it happens and only surfaces later as edits that mysteriously stop taking effect.
- [scope: hypergraph-orient reading state-node bodies over a hosted store | confidence: medium | evidence: steep-cell-5173] a tree call with `projection=full` returns topology-only payloads — it cannot substitute for children/get_node when bodies are needed. Retained as host-contract knowledge; orient no longer has a hosted path.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-fog-0600 — four skills + installer landed (M4)
- steep-cell-5173 — orient validated cold-start; body-reading recipe corrected (M5)
- patient-limit-9007 — directive-decision-node guidance added to hypergraph-record
- tiny-sunset-0847 — AGENTS.md onboarding added after blind test #1
- little-bar-4131 — blind test #2 validated AGENTS.md
- late-isle-6483 — fifth skill hypergraph-adopt + agents-block template
- stormy-dew-2969 — mode-B marker parentage corrected from field use
- tender-moss-3792 — adopt/reconcile/init updated for fork-import
- sweet-wave-7885 — skills are not installed by default; AGENTS.md corrected
- jolly-arbor-9572 — dogfooding symlinks committed; install-over-source bug fixed; --link added
- calm-sand-3399 — the five skills go single-path; acceptance grep returns zero hits
- vast-rain-4873 — parallel-work investigation: reconcile needs a publish-branch gate and the contributors-record rule
- placid-ridge-4035 — reconcile gains the maintainer-on-main rule and frontier guidance; record covers contributors
- clear-moss-4527 — record gains a tagging step built around restraint; adopt gains what travels and the pointer-tag routing
- shady-bay-7654 — record's step 7 rewritten around enumerating evidence, and the one editable-frontmatter guardrail
