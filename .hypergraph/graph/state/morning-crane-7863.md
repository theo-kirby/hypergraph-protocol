---
node_id: 5683b425-7e64-5829-8b78-6a69b75220f2
slug: morning-crane-7863
title: Adoption
created_at: '2026-08-07T20:01:01+00:00'
parents:
- cool-king-8586
summary: 'Adoption built, field-proven, and now MCP-free: mirror pull plus four adopt affordances compute the facts, while the agent writes every claim; working.'
flywheel:
  node_id: 67d32718-3dcf-5321-978a-212599c531b4
  slug: long-hall-1227
  revision: 7
  pushed_at: '2026-08-09T18:08:20+00:00'
  content_sha256: 469a062ae1e86b0b8a51b2fb37d1175911e2f339e354d701fd9472da21724b38
---
Status: working

## Current

- The adoption path is built, shipped, and field-proven end-to-end. Settled design held throughout: all-local import default, epoch-split only for scale, fork = import (slugs immutable), one-way mirror, artifacts stay on the archive [rec: vast-sky-3964].
- Epoch mechanism live: `epoch.marker` in config; `check` exempts record nodes created strictly before the marker from I2 (authoring-time validation never exempted; unresolvable marker is itself a violation); parentage rules per mode — full-import marker parents on the newest legacy node, mode B on the newest prehistory node, epoch-split marker is a parentless local root [rec: shady-quill-2790] [rec: stormy-dew-2969].
- Mirror integrity closed: `push --verify --against <export>` detects missing nodes, body-hash and summary drift, and revision skew; a mirror-only slug legend node is regenerated on every push; verify exempts config-declared `mirror_roots` (gap found live on a3go) [rec: careful-harbor-3902] [rec: humble-clover-7048].
- hypergraph-adopt skill shipped (mode A: import-as-fork with mandatory `archive:`; mode B: authored prehistory), with distillation guidance (per-branch subagent mining, id-prefix→slug resolution, honest statuses, user interview), the idempotent sentinel AGENTS.md block with contract reconciliation, and full `.hypergraph/AGENTS.md` onboarding [rec: late-isle-6483].
- Release 0.0.2 built with `hypergraph skills install` (skills + agents-block as package data) [rec: crisp-lake-4496] and now published to PyPI and verified from the public index — skills install works via uvx and the published CLI checks both adopted repos clean; the adopter onboarding pins on the dev checkout are removed [rec: rough-reef-5869].
- Field adoptions landed: a3go mode A (108-node legacy graph imported verbatim, 107 nodes epoch-exempt, check 0/0, verified mirror on fresh roots with the legacy graph frozen as archive) [rec: humble-clover-7048]; tbinn mode B (authored prehistory, frontier honestly led by a broken node, full mirror verified) [rec: stormy-dew-2969].
- Fork-import closed the last gap in the thrust: a full import **is** a fork, so the project re-publishes its whole imported history to a mirror it owns. `import --fork` files the archive's ids under `origin:` and omits `flywheel:`; `push --lineage` puts the archive lineage in the mirror record root's body; verification runs against the project's own roots alone. Shipped with tests, docs and skills [rec: copper-moss-3669] [rec: tender-moss-3792], then proven live on a3go — 108 creates, topology restored by re-parenting, `push --verify` exit 0 against the mirror alone [rec: northern-willow-0469].
- **Mode A no longer needs MCP.** The legacy export is `hypergraph mirror pull --record-node-id … [--state-node-id …]`, one call over every anchor, split locally by BFS into `record.json`/`state.json` — a node reachable from both anchor sets is an error, because the two graphs are disjoint by construction. It prints a draft `archive:` block on stderr [rec: silver-ember-3035] [rec: calm-sand-3399].
- **Four affordances compute the facts the adopting agent used to gather by hand**, so its budget goes to judgment [rec: calm-sand-3399]:
  - `adopt --survey` — git shape (first commit, contributors, timeline signals, highest-churn paths), source dirs, doc inventory, test framework, and **AGENTS.md/CLAUDE.md presence plus symlink status**. That last one was `ls -la` + `readlink` by hand, guarding a rule the skill states in prose (never break a `CLAUDE.md → AGENTS.md` symlink). Replaces roughly fifteen exploratory bash calls [rec: calm-sand-3399]. Timeline signals are three independent bodies of evidence — tags, directory births, quiet gaps — each printed as evidence and none as a decided era [rec: patient-sail-0175].
  - `adopt --init` — mints both roots and writes a *valid* config. Verified on a scratch repo: the result checks **0/0** [rec: calm-sand-3399]. It is now **root-aware**: exactly one parentless root of a kind is adopted (`adopted existing`), none is minted, and two raise by name rather than the CLI picking — so it lands from either direction, mode A's imported root included [rec: patient-sail-0175].
  - `adopt --marker <slug>` — records the epoch only after checking the slug resolves, and refuses to append a second `epoch:` block [rec: calm-sand-3399].
  - `adopt --resolve-prefixes --against <export>` — maps `[0-9a-f]{8,}` prefixes cited in tracked docs to slugs, **reporting ambiguity rather than guessing**; hex tokens matching no node are listed apart. Against this repo's own export it mapped all 53 ids with 0 ambiguous, correctly setting aside 1057 git SHAs [rec: calm-sand-3399].
- The **interview** stayed in the skill — prose, never a CLI verb — and is now **one staged sitting run at step 3**: Part 1 history (~10 questions feeding the prehistory nodes) and Part 2 the original five state questions, whose routing is unchanged — what didn't work and what in the docs is now false become negative knowledge and `broken` statuses; what is externally blocked becomes `blocked`; what you are deliberately not doing becomes a decision record node rather than a state claim [rec: calm-sand-3399] [rec: patient-sail-0175]. The agent seeds the generic questions with what `--survey` actually reported; a brain-dump substitutes for being asked; a declined interview is stated in the prehistory bodies rather than hidden [rec: patient-sail-0175].
- **The documented order now runs.** The skill is 8 steps — inventory, read, interview, `adopt --init`, history, marker, distillation, onboarding — with the roots minted *before* anything parents on them, and prehistory guidance widened from 1–3 to 3–10 nodes (one per era or workstream) [rec: patient-sail-0175].
- **An adoption is no longer write-once.** The skills and the AGENTS.md block adopt installs are copies in the adopter's repo, and until `hypergraph upgrade` there was no way to refresh them — 0.0.6's fixes shipped into a package whose *installed* skill still described the step order they fixed. Upgrade refreshes them in place, and `check` reports when they are behind (see fond-sail-3288) [rec: ancient-bluff-9706].
- Field-verified against a repo we did not write: mode B on a scratch clone of `ares` (347 commits, 5 contributors) walked all 8 steps to `check` **0/0**, with `--survey` naming six directory births in 0.38s where the gap heuristic found a single era spanning the whole history; mode A on a legacy-shaped export had `--init` adopt both imported roots; and a fresh-adopter `uv tool install hypergraph-protocol` + `hypergraph skills install` landed all five skills [rec: patient-sail-0175].
- **Field-verified on cadex — the first adoption run by someone other than the repo's author**, on 250 commits and 136 ADRs. `check` exits 0. The 14 prehistory nodes carry real causal structure rather than a flat list: three independent workstreams off the record root, converging on a marker parented on all six tips. Ten state nodes, 34 negative-knowledge entries, and an honest frontier — 1 broken, 1 blocked, 1 open, 7 working. Countable claims re-measured against the repo held (commit count, ADR count, surviving provenance tags, and a retired `CLAUDE.md` traced line-by-line into `AGENTS.md`), and post-adoption use includes a wrong count corrected by a **child node rather than an edit** [rec: vast-valley-5745].
- Two gaps the skill does not cover, both found on cadex [rec: vast-valley-5745]:
  - **It never checks that `.claude/skills/` is actually committable.** cadex's `.gitignore` opens with `.*` and un-ignores only `!/.hypergraph/`, so the graph travelled and the skills did not — a clone would have received an AGENTS.md instructing it to run `hypergraph-orient` with no skill to run. Nothing detects this: `adopt` does not read `.gitignore` and `check` reads the graph, not the repo [rec: vast-valley-5745].
  - **The 3–10 prehistory guidance was exceeded at 14**, on a project with a pre-repo life and six parallel verticals, where the nodes still read as eras rather than a changelog. The guidance looks too tight rather than the adoption wrong [rec: vast-valley-5745].
- **One field deviation is better than the skill's own text and should replace it**: cadex parented its epoch marker on **every** prehistory tip, not the newest one. That makes the marker the single record tip, so one high-water mark covers the whole authored history — which the current rule ("mode B on the newest prehistory node") does not guarantee when prehistory ends in parallel workstreams [rec: vast-valley-5745].
- Acceptance test passed: a fresh agent with no protocol context completed the full loop in a3go — orient in 6 calls, genuine frontier work (GEO-1 precondition: d=1 boards proven exactly 2D Go, corner-flip endpoint measured), causally-parented record, no state writes, librarian reconcile, mirror verify clean — zero protocol violations [rec: fond-tree-4727].

## Negative knowledge

- [scope: importing legacy Flywheel graphs into the local backend | confidence: high | evidence: vast-sky-3964 | decision: vast-sky-3964] Artifacts do not survive import — the local backend has no artifact operation, so archived artifacts stay on the legacy Flywheel graph; the `archive:` config reference is mandatory in mode A for this reason, and the mirror record root now states the loss explicitly via `push --lineage`.
- [scope: generating protocol content from a tool | confidence: high | evidence: calm-sand-3399 | decision: calm-sand-3399] the CLI must never generate prose — no prehistory bodies, no `## Current` claims, no negative-knowledge entries — even though it has the facts to fill the templates. A claim nobody derived from evidence they read is not re-derivable, which breaks I8 by definition, and template-filling is precisely the aspirational output adopt's guardrails exist to prevent. The line that holds: the CLI computes facts, the agent writes claims.
- [scope: documented multi-step agent workflows | confidence: high | evidence: patient-sail-0175 | decision: patient-sail-0175] a workflow's step *order* is untested until someone executes it literally. hypergraph-adopt authored prehistory in step 2 and minted the roots in step 5 for its entire life; `new record` needs a root to parent on, so the documented sequence hard-errored at `adopt --init` (and `--force` did not recover), leaving hand-written config — the exact failure `--init` exists to prevent — as the agent's only move. Every test called `--init` on an empty graph, so nothing caught it. A workflow an adopter reads once needs a test that scripts the steps *as written*.
- [scope: inferring project eras from git history | confidence: high | evidence: patient-sail-0175 | decision: patient-sail-0175] commit-gap clustering is not an era signal on an actively-worked repo: `ERA_GAP_DAYS = 21` found one era spanning all 347 commits of `ares`, while first-commit-per-top-level-directory found six boundaries on the same history. Gaps are kept because they are the strongest signal on a paused-and-revived repo, but they are one signal of three and must be printed as evidence, never as a decided era.
- [scope: adopting a graph you do not own | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] preserving the source node_ids as the *push target* silently orphans the whole imported history: the nodes are on Flywheel, on a graph another account owns, so push omits them and the project's own mirror stays a stub. Provenance and push target must be separate fields, and mirror verification must never include the archive in its export.

## Provenance

- vast-sky-3964 — Operator directive opening the adoption thrust; settled epoch design, fork-by-import, storage default, mirror policy, AGENTS.md approach, and both dogfooding targets
- shady-quill-2790 — M1: epoch support in the checker
- careful-harbor-3902 — M2: push --verify + slug legend, live-proven
- late-isle-6483 — M3: hypergraph-adopt skill + agents-block template
- crisp-lake-4496 — M4: 0.0.2 built with skills install; publish blocked on credentials
- humble-clover-7048 — M5: a3go adopted (mode A)
- stormy-dew-2969 — M6: tbinn adopted (mode B); mode-B marker rule corrected
- fond-tree-4727 — M7: fresh-agent acceptance loop held
- rough-reef-5869 — 0.0.2 published; adopters un-pinned; thrust tail closed
- copper-moss-3669 — fork-import direction opened: adopted projects mirror their full history
- tender-moss-3792 — fork-import shipped (tooling, docs, skills)
- northern-willow-0469 — a3go migrated live; fork-import field-proven
- silver-ember-3035 — mirror pull replaces the MCP export path for mode A
- calm-sand-3399 — adopt affordances (survey/init/marker/resolve-prefixes); the no-generated-prose line
- patient-sail-0175 — adoption fixed end-to-end after walking it against an outside repo: root-aware `--init`, 8-step order, timeline signals, staged interview, 3–10 prehistory nodes
- ancient-bluff-9706 — the installed skills and AGENTS.md block became refreshable, closing the write-once gap an adoption used to leave
- vast-valley-5745 — cadex audited: the path holds on a third-party run, and three gaps it does not cover
