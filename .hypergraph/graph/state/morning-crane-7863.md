---
node_id: 5683b425-7e64-5829-8b78-6a69b75220f2
slug: morning-crane-7863
title: Adoption
created_at: '2026-08-07T20:01:01+00:00'
parents:
- cool-king-8586
summary: Both modes built, shipped and field-proven across four adoptions, three of them run by someone other than the repo's author; MCP-free, with four affordances computing facts and the agent writing every claim.
flywheel:
  node_id: 67d32718-3dcf-5321-978a-212599c531b4
  slug: long-hall-1227
  revision: 11
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: 049835e4028bab75ca7f552b0e6cab008cb215f2452f9a13d1057717638e2fd2
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

Bringing a repo that already has a past under the protocol. Built, shipped, and field-proven end to end in both modes [rec: vast-sky-3964].

- **The settled design held throughout**: all-local import by default, epoch-split only for scale, fork = import with slugs immutable, a one-way mirror, and artifacts staying on the archive [rec: vast-sky-3964]. Two modes: **A**, import an existing hosted graph verbatim as the fork with a mandatory `archive:` block; **B**, author prehistory from the repo itself [rec: late-isle-6483].
- **The epoch mechanism is live**: `epoch.marker` in config, `check` exempting record nodes created strictly before it from I2 with authoring-time validation never exempted and an unresolvable marker itself a violation, and parentage rules per mode [rec: shady-quill-2790] [rec: stormy-dew-2969].
- **A full import *is* a fork**, so the project re-publishes its whole imported history to a mirror it owns: `import --fork` files the archive's ids under `origin:` and omits `flywheel:`, `push --lineage` puts the archive lineage in the mirror record root's body, and verification runs against the project's own roots alone [rec: copper-moss-3669] [rec: tender-moss-3792] [rec: northern-willow-0469].
- **Mode A no longer needs MCP**: `hypergraph mirror pull` is one call over every anchor, split locally by BFS into `record.json`/`state.json`, with a node reachable from both anchor sets an error because the two graphs are disjoint by construction [rec: silver-ember-3035] [rec: calm-sand-3399].
- **Four affordances compute the facts the adopting agent used to gather by hand, so its budget goes to judgment** [rec: calm-sand-3399]. `adopt --survey` reports git shape, source dirs, doc inventory, test framework and AGENTS.md/CLAUDE.md presence *plus symlink status*, replacing roughly fifteen exploratory bash calls; its timeline signals are three independent bodies of evidence — tags, directory births, quiet gaps — each printed as evidence and none as a decided era [rec: patient-sail-0175]. `adopt --init` mints both roots and writes a valid config, and is **root-aware**: exactly one parentless root of a kind is adopted, none is minted, and two raise by name rather than the CLI picking [rec: patient-sail-0175]. `adopt --marker` records the epoch only after checking the slug resolves. `adopt --resolve-prefixes` maps hex prefixes cited in tracked docs to slugs, **reporting ambiguity rather than guessing** — 53 ids mapped with 0 ambiguous against this repo's export, correctly setting aside 1057 git SHAs.
- **The interview stayed in the skill — prose, never a CLI verb** — as one staged sitting at step 3: Part 1 history, Part 2 the original five state questions, whose routing is unchanged (what didn't work and what in the docs is now false become negative knowledge and `broken` statuses; what is externally blocked becomes `blocked`; what you are deliberately not doing becomes a decision record node) [rec: calm-sand-3399] [rec: patient-sail-0175].
- **The documented order now runs**: 8 steps with the roots minted before anything parents on them, and prehistory widened from 1–3 to 3–10 nodes [rec: patient-sail-0175].
- **Four field adoptions, and three were run by someone other than the repo's author.** a3go (mode A, 108 nodes) and tbinn (mode B) landed first [rec: humble-clover-7048] [rec: stormy-dew-2969]. `ares` walked all 8 steps to check 0/0 on a repo we did not write [rec: patient-sail-0175]. **cadex** — 250 commits, 136 ADRs — produced 14 prehistory nodes with real causal structure, ten state nodes, 34 negative-knowledge entries and an honest frontier, with countable claims re-measured against the repo [rec: vast-valley-5745]. **neural-whoop** — 189 legacy nodes, mode A, by an agent that could not ask a question — checks 0/0 with the archive verifiably untouched and identity preserved verbatim, and is the first real exercise of the mode A path [rec: clever-ledge-6588].
- **Nine documentation defects came out of that unattended run, and the costly ones were mechanical** [rec: clever-ledge-6588]: `## State Impact` is refused in a body and must come from `--impact`, which itself prepends `- target: `; state slugs are minted and cannot be chosen, so readable `NEW <kebab-name>` targets never resolve to the nodes you then mint; and advancing the HWM to the marker rather than to the record tips left 111 nodes unreconciled on a wide DAG. A **mode A walkthrough** now documents the ordering that works and why it is not the numbered one.
- **Three gaps that remain open, all found on cadex** [rec: vast-valley-5745]: nothing checks that `.claude/skills/` is actually *committable* — cadex's `.gitignore` would have shipped a clone an AGENTS.md instructing it to run a skill that did not travel; the 3–10 prehistory guidance was exceeded at 14 on a project with six parallel verticals, and the guidance looks too tight rather than the adoption wrong; and one **field deviation is better than the skill's own text** — cadex parented its epoch marker on *every* prehistory tip, which makes the marker the single record tip so one high-water mark covers the whole authored history.
- **Tags now travel, and a repo that adopted before they did is repaired rather than re-imported** [rec: fresh-spire-9002] [rec: clear-moss-4527]. `import` resolves the source's tag ids through the **union** of `graph_tags` across every node — only 130 of 189 echoed the vocabulary, so a single node's copy loses a third of the graph — writes the names onto each node and the vocabulary into `tags.yml`, and transliterates deterministically while reporting every rename. **Pointer-tag history is routed, not modelled**: all six hops of one chain carry a timestamp and none carries a reason, and a move *with* a reason is a decision, which is a record node rather than a third home in frontmatter [rec: simple-ocean-1716].
- **An adoption is no longer write-once.** The skills and the AGENTS.md block are copies in the adopter's repo; `hypergraph upgrade` refreshes them and `check` reports when they are behind [rec: ancient-bluff-9706].

## Negative knowledge

- [scope: importing legacy Flywheel graphs into the local backend | confidence: high | evidence: vast-sky-3964 | decision: vast-sky-3964] Artifacts do not survive import — the local backend has no artifact operation, so archived artifacts stay on the legacy Flywheel graph; the `archive:` config reference is mandatory in mode A for this reason, and the mirror record root now states the loss explicitly via `push --lineage`.
- [scope: generating protocol content from a tool | confidence: high | evidence: calm-sand-3399 | decision: calm-sand-3399] the CLI must never generate prose — no prehistory bodies, no `## Current` claims, no negative-knowledge entries — even though it has the facts to fill the templates. A claim nobody derived from evidence they read is not re-derivable, which breaks I8 by definition, and template-filling is precisely the aspirational output adopt's guardrails exist to prevent. The line that holds: the CLI computes facts, the agent writes claims.
- [scope: documented multi-step agent workflows | confidence: high | evidence: patient-sail-0175 | decision: patient-sail-0175] a workflow's step *order* is untested until someone executes it literally. hypergraph-adopt authored prehistory in step 2 and minted the roots in step 5 for its entire life; `new record` needs a root to parent on, so the documented sequence hard-errored at `adopt --init` (and `--force` did not recover), leaving hand-written config — the exact failure `--init` exists to prevent — as the agent's only move. Every test called `--init` on an empty graph, so nothing caught it. A workflow an adopter reads once needs a test that scripts the steps *as written*.
- [scope: inferring project eras from git history | confidence: high | evidence: patient-sail-0175 | decision: patient-sail-0175] commit-gap clustering is not an era signal on an actively-worked repo: `ERA_GAP_DAYS = 21` found one era spanning all 347 commits of `ares`, while first-commit-per-top-level-directory found six boundaries on the same history. Gaps are kept because they are the strongest signal on a paused-and-revived repo, but they are one signal of three and must be printed as evidence, never as a decided era.
- [scope: enumerating what an adoption drops | confidence: high | evidence: fresh-spire-9002, clever-ledge-6588] a category of data can be dropped silently by an adoption **because the protocol has no word for it**, not because the backend cannot carry it. Tags were filed under SPEC's "future work — the shipped storage does not implement" and that sentence was true only of the local adapter; the hosted backend had create/assign/update/delete the whole time. Nothing reported the loss, and it was found by counting a real archive rather than by reading the code. Measure an adoption's *inputs* against its outputs field by field; an unrepresentable category is invisible to every check by construction.
- [scope: adopting a graph you do not own | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] preserving the source node_ids as the *push target* silently orphans the whole imported history: the nodes are on Flywheel, on a graph another account owns, so push omits them and the project's own mirror stays a stub. Provenance and push target must be separate fields, and mirror verification must never include the archive in its export.

## Provenance

- vast-sky-3964 — Operator directive opening the adoption thrust and its settled design
- shady-quill-2790 — epoch support in the checker (M1)
- careful-harbor-3902 — push --verify and the slug legend, live-proven (M2)
- late-isle-6483 — the hypergraph-adopt skill and the agents-block template (M3)
- crisp-lake-4496 — 0.0.2 built with skills install (M4)
- humble-clover-7048 — a3go adopted, mode A (M5)
- stormy-dew-2969 — tbinn adopted, mode B; the mode-B marker rule corrected (M6)
- fond-tree-4727 — the fresh-agent acceptance loop held (M7)
- rough-reef-5869 — 0.0.2 published; adopters un-pinned
- copper-moss-3669 — fork-import direction opened
- tender-moss-3792 — fork-import shipped across tooling, docs and skills
- northern-willow-0469 — a3go migrated live; fork-import field-proven
- silver-ember-3035 — mirror pull replaces the MCP export path for mode A
- calm-sand-3399 — the four adopt affordances and the no-generated-prose line
- patient-sail-0175 — adoption fixed end to end against an outside repo: root-aware init, the 8-step order, the staged interview
- clever-ledge-6588 — neural-whoop adopted with no author available; nine documentation defects and the mode A walkthrough
- ancient-bluff-9706 — an adoption stops being write-once
- vast-valley-5745 — cadex audited: the path holds on a third-party run, and three gaps it does not cover
- fresh-spire-9002 — the tag loss measured on a real archive
- simple-ocean-1716 — tag names travel; pointer history is routed to the epoch marker
- clear-moss-4527 — import carries tags; the adopt skill's wrong claim about taxonomies fixed
- late-sage-5549 — compacted, with the upgrade path re-homed underneath as its child
