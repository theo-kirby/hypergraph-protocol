---
node_id: f4950c54-f0a6-5d9a-a731-2405473d719b
slug: sweet-wave-7885
title: 'Operator decision: one Flywheel account for arm B, declared as a confound; relaunch parked'
created_at: '2026-08-09T09:49:28+00:00'
parents:
- staid-field-2723
summary: ''
flywheel:
  node_id: 487d5de9-f17f-5bc5-b1bc-70d9d044232b
  slug: ancient-wildflower-5557
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 423521c14d812625ecc0ad612437b7ba11bb98c250df67ef8ddb871a3f9e20dd
  parents_sha256: 994a58c570e634ce7152b05d5a6de0e3307ee6e8d7b65e082e27cff6d8b2afb6
  parents:
  - b3990a6a-c2a0-53a7-8b07-e74a4b332186
---
## What

Operator decision, 2026-08-09: the relaunch runs **arm B's three seeds on one
Flywheel account**, not three. Three accounts could not be created. The
consequence is accepted rather than allowed to block the experiment indefinitely.

Also decided in the same pass: the relaunch itself is **parked**. The hardened
harness is finished and verified, and nothing spends until the Operator picks it
back up.

Implemented alongside the decision, so the next session starts from a coherent
state rather than re-deriving it:

- `preflight --shared-flywheel` / `run --shared-flywheel` — explicit opt-in. Without
  it, a multi-seed arm-B launch still hard-fails, so the shared account can never
  become the accidental default.
- Under the flag, preflight captures the account's **full node-id set** immediately
  before launch to `research/runs/flywheel-baseline.json`. Verified live against
  the rotated key: 458 ids.
- An unreadable account fails either way. Unattributable is as disqualifying as
  unisolated.
- `METRICS.md` gains a **DECLARED CONFOUND** section under the design constraints.

## Why

Follows `staid-field-2723`, which hardened the harness on the assumption of one
Flywheel account per arm-B seed — the fix for the first run's worst isolation
defect, where all three seeds shared an account holding 458 nodes from unrelated
projects and one spent seven `get_node` calls reading a June football campaign.

The assumption did not survive contact. Given a choice between blocking the
experiment on an unavailable resource and running with a known, bounded, stated
weakness, the Operator chose the latter. That is a legitimate call: the confound
is **asymmetric** — arms A and C keep full isolation, because their memory is
per-box files and a per-run repository — so it degrades one arm's result rather
than the comparison as a whole, and a reader who discounts arm B entirely still
has a valid A-vs-C comparison.

What is *not* legitimate is absorbing the weakness quietly, which is how the first
run's defects survived to publication. Hence the opt-in flag, the confound section
in the pre-registration, and the baseline capture.

## Method

Isolation is impossible with one account; **attribution** is not. Preflight pages
`flywheel_list_nodes` (`owners:["me"]`) to exhaustion and records every node id it
finds, before any box exists. Anything present afterwards and absent from the
baseline was created in the run window.

That also repairs the cold-start eligibility gate (`had_prior_state`, METRICS.md
§2): it reads only nodes created after the baseline, so it cannot be satisfied by
a sibling seed's writes or by pre-existing unrelated history.

Verified live with the rotated key:

    uv run research/lab.py preflight --arms git flywheel hypergraph --seeds 3 \
        --no-create-repos --shared-flywheel
    # preflight: PASS (21/21); 458 pre-existing node(s) recorded

Credential state at the time of this decision: `OPENROUTER_API_KEY`,
`GITHUB_TOKEN` and `FLYWHEEL_API_KEY` rotated by the Operator; `BOX_API_KEY`
deleted outright, which is correct and costs nothing — `box_ctl` shells out to the
`box` CLI, which carries its own auth, and the lab resolves `BOX_API_KEY` only to
display it in `creds`. A dead value for it remains in the local `.env`.

Separately diagnosed, and the answer to why `/hypergraph-record` and
`/hypergraph-reconcile` kept resolving as unknown skills: **they are not installed
anywhere on the dev machine.** `~/.claude/skills/` holds only Flywheel's eight, and
this repo ships no project-level `.claude/skills`. `AGENTS.md` claimed otherwise,
and that claim is what made it look like a harness fault. Corrected there.

## Result

The relaunch is unblocked but deliberately not started.

- Preflight **21/21** with `--shared-flywheel`; **19/20** without it, failing only
  on the three keys that do not exist.
- 159 tests pass, including four that hold the confound honest: the shared account
  is refused by default, accepted only with an explicit flag, recorded as its own
  named check when accepted, and fails outright when unreadable. A fifth asserts
  METRICS.md actually contains the declaration — a confound that is not written
  down is not declared.
- **The confound does not touch arms A and C.** They publish to per-run
  repositories the harness names and hold their memory in per-box files.

Named and **not implemented**, for whoever resumes: a harness-seeded per-run root
node in Flywheel, and a per-run tag on every node the run creates. Both narrow
attribution further; neither restores isolation. Only separate accounts do that.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: cd6dcb6102368e9add516d133026825795f5d50a

## State Impact

- target: protocol-benchmark-4417 — Operator decision (2026-08-09): arm B's three seeds run on ONE Flywheel account, not three; three accounts could not be created. Isolation for arm B is genuinely lost — its seeds can list, read and overwrite each other's nodes — and the confound is now DECLARED in METRICS.md rev-1 rather than absorbed. It is ASYMMETRIC: arms A and C keep full isolation (per-box files, per-run repository each), so a reader who discounts arm B entirely still has a valid A-vs-C comparison. What survives for arm B is attribution, not isolation: preflight captures the account's full node-id set before launch (verified live: 458 ids) so every node created in the run window is identifiable, and had_prior_state reads only nodes created after that baseline. Opt-in via --shared-flywheel; without it a multi-seed arm-B launch still hard-fails. Preflight is 21/21 with the flag. The relaunch is unblocked and deliberately PARKED — nothing spends until the Operator resumes. Remaining unimplemented mitigations: a harness-seeded per-run root node and a per-run tag; neither restores isolation.
- target: fair-field-3265 — the shared-account lesson now has its counterpart: when isolation is unavailable, capture a baseline before launch so the work stays attributable, and declare the loss in the pre-registration rather than absorbing it. Attribution is the salvageable half of isolation. Also recorded: a dead credential left in a dotfile is not a risk but is not tidy either — BOX_API_KEY was deleted upstream and the lab never used it, because box_ctl shells out to the `box` CLI which carries its own auth.
- target: dry-wildflower-2260 — the five skills are NOT installed by default anywhere, and AGENTS.md claimed they were ('also installed in ~/.claude/skills'). That stale claim is why `/hypergraph-record` and `/hypergraph-reconcile` resolved as unknown skills for a whole session, and why it read as a harness fault rather than a missing install. AGENTS.md corrected: the workflow is the SKILL.md file and can be followed directly; `hypergraph skills install` (project) or `--user` (global) is what makes them loadable. The benchmark boxes are unaffected — pi never reads .claude/skills, and the Claude Code path already runs `skills install --user` during provisioning.
