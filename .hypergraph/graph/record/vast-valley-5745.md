---
node_id: 479dd8ea-fe3c-5502-b6f2-f268b1d528c5
slug: vast-valley-5745
title: hypergraph upgrade overwrites the project-specific half of its own AGENTS.md block
created_at: '2026-08-09T18:05:54+00:00'
parents:
- tiny-stone-3934
summary: 'Field audit of cadex''s mode-B adoption, and the first real-repo run of hypergraph upgrade. The adoption held; upgrade deleted the contract-reconciliation clause and epoch note that the adopt skill requires inside the sentinels. Two further gaps: adopt never checks that .claude/skills/ is committable, and a pre-stamp repo cannot report a CLI-is-older skew.'
flywheel:
  node_id: d2081867-4bcc-5307-bfe8-9562808be728
  slug: bold-river-8361
  revision: 0
  pushed_at: '2026-08-09T18:08:20+00:00'
  content_sha256: b72695705d4a2d8997a5cb9c4131f49d5f8f766e560a0b837f5ed25390c9ecd1
---
## What

Audited cadex's mode-B adoption — the first adoption run entirely by someone
other than its author, on a 250-commit repo with 136 ADRs — and ran
`hypergraph upgrade` there for the first time outside a test fixture. The
adoption held up. `upgrade` did not, in one specific and repeatable way.

**`upgrade` destroys project-specific prose *inside* the sentinels.** It replaced
the whole `<!-- hypergraph:begin -->` block with the shipped template and deleted
two paragraphs cadex needed:

- the clause reconciling the record graph with `docs/DECISIONS.md` — **which the
  adopt skill's step 8 requires be written**, under "contract reconciliation";
- the epoch-marker note naming the marker slug and the prehistory node count.

Prose *outside* the sentinels survived verbatim — I diffed the file with the
block stripped and it is byte-identical. So `fond-sail-3288`'s claim, "the
AGENTS.md block is replaced between its sentinels with the adopter's own prose
intact", is true of the file and false of the block. The two skills disagree:
`adopt` writes per-project content into the sentinels, and `upgrade` treats
everything in there as ours to overwrite.

**Second finding, from the same audit: the skills were not committable.** cadex's
`.gitignore` opens with `.*` and un-ignores `!/.hypergraph/`. The graph therefore
travelled and `.claude/skills/` did not. A clone would have received an AGENTS.md
instructing it to run `hypergraph-orient`, and no skill to run. Nothing in the
adoption detects this: `adopt` never inspects `.gitignore`, and `check` reads the
graph, not the repo.

**Third: the skew was real and undetectable.** cadex ran a 0.0.6 CLI against
0.0.7 skills. With no `hypergraph_version:` stamp, `check` emits only the
"predates the stamp" info — correct by its own rules, and it means the one case
where the *CLI* is the old half cannot be reported on any pre-stamp repo.

## Why

cadex was adopted as a deliberate field test of the 0.0.7 adoption path. The
value of that test is entirely in what it caught, so the findings are recorded
here rather than only fixed there.

## Method

Audited against the eight steps of the adopt skill, verifying countable claims
independently instead of trusting the nodes: 248 commits at the adoption commit
(stated 248), highest ADR 136 (stated 136), 16 surviving `[VibeCAD-era]` tags,
and 286 non-blank lines of a retired `CLAUDE.md` traced into `AGENTS.md` with 4
absent — 3 the retired header, 1 a test count deliberately corrected by a later
record node. `upgrade` was run with `--dry-run` first; the dry run is what caught
the block defect, before it was applied.

## Result

**The adoption itself is evidence the path works.** `check` exits 0. Fourteen
prehistory nodes carry real causal structure — three independent workstreams off
the root, converging on a marker parented on all six tips. Ten state nodes, 34
negative-knowledge entries, and an honest frontier (1 broken, 1 blocked, 1 open,
7 working) rather than everything-is-working. Five post-adoption record nodes
show the protocol in live use, including a **correction published as a child
node** rather than an edit, after a count was found wrong.

**Two deviations from the skill, both defensible, one worth adopting into it:**

- 14 prehistory nodes against a stated 3–10. They read as eras and workstreams,
  not a changelog, on a project with a pre-repo life and six parallel verticals.
  The guidance is probably too tight, not the adoption wrong.
- The marker parents on **all six** prehistory tips, where the skill says "parent
  = the newest prehistory node". Its stated reason is better than the skill's
  text: it makes the marker the single record tip, so one high-water mark covers
  the whole authored history. **The skill should say this.**

**Fixed in cadex, not here**: `.gitignore` un-ignores `/.claude/skills/` (25 files
now travel), the CLI is on 0.0.7, the config is stamped, `.hypergraph/AGENTS.md`
gained a "Getting the tool" section naming both upgrade commands, and the two
deleted paragraphs were restored by hand with a warning naming the block as
overwritable. cadex's own graph records it as `twilight-sail-5604`.

**Not fixed anywhere**: the three defects above are open in this project.

## Negative knowledge

`--dry-run` on a command that rewrites an adopter's files is not a convenience,
it is the only thing between a shipped default and silent data loss in someone
else's repo. `upgrade` shipped with the belief that sentinels made the write
safe; the sentinels are exactly where the unsafe content lives, and one dry run
in a real repo showed it. A destructive default is only visibly wrong on a repo
that used the feature it destroys — which is never the fixture that tests it.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: b25e485cde5436042683e7b725b20e52412a4d0d

## State Impact

- target: fond-sail-3288 — broken: running 'hypergraph upgrade' on a real adopted repo deletes project-specific prose from inside the <!-- hypergraph:begin --> sentinels. The claim 'the adopter's own prose intact' holds for the file (verified byte-identical outside the block) and fails inside it, which is where the adopt skill's step 8 requires per-project content: cadex lost its docs/DECISIONS.md contract-reconciliation clause and its epoch-marker note. The two skills disagree — adopt writes there, upgrade overwrites it — and the same command deliberately reports .github/workflows/ drift rather than overwriting, because adopters customise those. New negative knowledge: --dry-run is the only guard between a destructive default and data loss in someone else's repo, and a destructive default is invisible on any fixture that does not use the feature it destroys.
- target: morning-crane-7863 — Field-verified on cadex, the first adoption run by someone other than the repo's author: check exits 0, 14 prehistory nodes carry real causal structure (three workstreams off the root converging on a marker parented on all six tips), 10 state nodes with 34 negative-knowledge entries and an honest frontier of 1 broken / 1 blocked / 1 open. Two gaps the skill does not cover: it never checks that .claude/skills/ is actually committable — cadex's repo-wide '.*' ignore rule silently excluded them, so a clone would have received the AGENTS.md contract with no skills to run it — and its 3-10 prehistory guidance was exceeded at 14 for a project with a pre-repo life and six verticals, where the nodes still read as eras rather than a changelog. One deviation is better than the skill's own text and should be folded into it: parenting the epoch marker on every prehistory tip rather than the newest one makes the marker the single record tip, so one high-water mark covers the whole authored history.
