---
node_id: 3a3b9273-ea31-5b7a-a9ff-5fccd70caef3
slug: patient-sail-0175
title: 'Fixed adoption end-to-end: ordering, front door, era signals, prehistory interview'
created_at: '2026-08-09T13:25:38+00:00'
parents:
- long-peak-1620
- wise-river-3571
summary: Three reproduced defects and two gaps in the adoption path, fixed and verified against a 347-commit outside repo.
flywheel:
  node_id: 93da6620-6598-5ca5-8681-b6a488d02831
  slug: frosty-heart-4991
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: fddca5ebce41c8a605f5b751107953251e4b5927f6196673cb2e95ed276f1788
  parents_sha256: 1f16f74c71bf191444ba444b5a20a7af5f4a2d665bc311fbe8514ec22fe11a8a
  parents:
  - a7a3106b-d4ea-58aa-88bc-5184bafb7fcd
  - f6b6de60-6126-5155-b7c0-3213b995beb2
---
## What

Fixed adoption end-to-end after walking it against a real outside repo (`~/ares`,
347 commits, 5 contributors, never adopted). Three defects reproduced and fixed, two
gaps closed:

1. **The documented step order did not run.** The skill authored prehistory in step 2
   and minted the roots in step 5, but `new record` needs a root to parent on — so an
   agent following the skill literally created one, and `adopt --init` then refused
   (`error: the record graph already has a root: rising-crane-5399`), `--force`
   included. The only move left was hand-writing the config: the exact failure `--init`
   exists to prevent. Mode A collided the same way in reverse — `import --fork` lands
   the legacy root and `--init` refused to mint over it.
2. **The README's front door was the wrong path**: Quickstart opened with
   `./install.sh`, which needs a clone of this repo, while adopters never clone it
   [state: weathered-union-7494]. `uv tool install hypergraph-protocol` +
   `hypergraph skills install` appeared nowhere; adopt was prose after the quickstart.
3. **The era heuristic produced nothing on a real repo.** `ERA_GAP_DAYS = 21` found a
   single era spanning all 347 ares commits.

Gaps: prehistory was capped at "1–3" nodes, too few for a year-old project; and
nothing in the workflow asked the author what happened.

## Why

Follows the 0.0.5 release and the CI publish work [rec: long-peak-1620]. Adoption is
the path every outside project takes into the protocol and the one workflow never run
by anyone but us — so it is the workflow whose defects stay invisible longest. Walking
it against a repo we did not write is what surfaced all three.

## Method

`tools/hypergraph.py`:

- **`ensure_root_node(graph_dir, kind, title, body) -> (slug, minted)`** beside the
  existing `create_root_node`: exactly one parentless node of that kind → adopt it;
  none → mint through the existing path; more than one → raise, naming them, because
  that is genuinely ambiguous and the CLI must not pick. `adopt_init` calls it for
  both kinds and prints `(adopted existing)` or `(minted)`. `create_root_node` stays
  strict — it is the primitive, `ensure_root_node` is the policy.
- **Timeline signals** replace the single candidate-era list. `adopt_survey` computes
  the layout first and passes its top-level source dirs into
  `survey_git(repo, source_dirs=…)`, which gains `tags` (`git tag --sort=creatordate`,
  empty list when there are none — it must degrade silently, and both our repos have
  none) and `dir_births` (first commit date touching each top-level dir). The existing
  `eras` key keeps its shape so `--json` consumers do not break. `print_survey` prints
  three labelled subsections under `## Timeline signals`, each as evidence, and prints
  nothing at all for a signal with nothing to say.

`skills/hypergraph-adopt/SKILL.md`: the workflow becomes 8 steps — inventory, read,
**interview**, `adopt --init`, history, marker, distillation, onboarding. Step 4
states why it sits there and not later. A new **staged interview** section carries ~10
history questions (feeding the prehistory nodes) plus the existing 5 state questions
moved verbatim from the old step 4, with the instruction to seed the generic questions
with what `--survey` actually reported. Three rules: a brain-dump substitutes for the
questions; a declined interview is recorded in the prehistory bodies, not hidden; and
answers are evidence, not prose to paste. Prehistory guidance goes 1–3 → 3–10, one
node per era or workstream, with the "honest summary, never event-by-event
reconstruction" rule kept adjacent.

`README.md`: a new `## Install` section before Quickstart carrying the only path an
adopter needs; Quickstart split into two labelled routes (new project → init, existing
→ adopt); the command blocks made bare `hypergraph` throughout; `./install.sh` moved
to a "Developing the protocol itself" note near the repo map.

`tests/`: the adoption tests moved out of `test_mirror.py` (they sat under an
`# adoption` banner and are not mirror tests) into a new `tests/test_adoption.py`,
matching the `test_collaboration.py` precedent, plus six new tests — the ordering
regression scripting the documented mode-B sequence step by step, `--init` adopting an
existing root in both the mode-A and mode-B shapes, `--init` refusing two parentless
roots by name, tags/`dir_births` on a fixture repo and their silent degradation, and a
README doc assertion in the style of `test_packaging.py`.

## Result

290 tests pass; `sync` clean (0 violations, 0 warnings, 0 drift).

Verified end-to-end against real repos, not fixtures:

- **The defect that started this**: replaying the old broken order — author a root,
  then `adopt --init` — now prints `record root: old-timber-2155 (adopted existing)`
  instead of erroring.
- **Mode B on a scratch clone of `~/ares`** (the original never written to): `--survey`
  reported six directory births — `dashboard/` 2026-02-23, `cron/` 04-15,
  `agents/`+`bin/`+`tools/` 04-22, `api/` 05-26 — in 0.38s over 347 commits, with no
  tags and no quiet-gap section (the gap heuristic still finds one era there). Walked
  all 8 steps: 5 prehistory nodes (one per era), epoch marker, 6 distilled state nodes,
  HWM advance, AGENTS.md block appended to the existing CLAUDE.md. `export` → `render`
  → `check` **exit 0, 0 violations, 0 warnings**. The interview was declined (a
  verification adoption on a clone, not the author's own), so every prehistory body
  says so in as many words — which is the new rule, exercised.
- **Mode A** on a legacy-shaped export: `import --fork` → `adopt --init` adopted *both*
  imported roots (`royal-anchor-0001`, `amber-harbor-0101`) → `--marker` → check exit
  0. The `mirror pull` leg was not run: a3go is not on this machine.
- **Fresh-adopter simulation**: `uv tool install hypergraph-protocol` into an isolated
  tool dir installed 0.0.5, and `hypergraph skills install` in a scratch repo landed
  all five skills — the README's Install block is literally what was run.

Measured: directory births produce four era-shaped boundaries on `ares` where the
quiet-gap heuristic produces none. Tags fired on neither of our repos nor on ares, so
they are kept for the repos that have them and are silent otherwise.

Not done: no release. 0.0.5 is on PyPI and this lands unreleased. Commit-rate
change-point detection was considered and declined — tags plus directory births
already split usefully, and change points can suggest boundaries meaning nothing to
the author.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol
- branch: main
- commit: c42284cb5da4b1885120b83d2f6f673c9abde6ff

## State Impact

- target: morning-crane-7863 — adopt --init is now root-aware (adopts an existing root, refuses only genuine ambiguity), the skill's step order runs as written (8 steps, init before authoring), --survey reports timeline signals (tags + directory births + quiet gaps) instead of one useless era list, prehistory guidance is 3-10 nodes, and a staged author interview is part of the workflow
- target: weathered-union-7494 — the README front door is the PyPI path (uv tool install + hypergraph skills install), with adopt promoted from prose-after-quickstart to one of two labelled routes in
