---
node_id: 83e18828-5a08-5ad8-8bd8-71e374e5465d
slug: scarlet-orchard-8774
title: 'M2: pi/OpenRouter harness, experiment driver, spend guard; cold start holds on both harnesses'
created_at: '2026-08-08T17:12:38+00:00'
parents:
- twilight-wood-1934
summary: ''
---
## What

Switched the benchmark's harness from Claude Code to **pi** (pi.dev) against
OpenRouter on `deepseek/deepseek-v4-pro`, on Operator direction, and built the
rest of M2: a harness abstraction, the experiment driver, an OpenRouter spend
guard, the shared mission, and the cold-start continuation prompt. Proved the pi
path live on one box.

## Why

Operator directive: run all nine arms concurrently on a metered API rather than
staggering them against a Claude subscription. The reasoning is the risk profile,
not the price. The previous plan's failure mode was a subscription quota wall
landing mid-run, which would truncate arms **unevenly** — the charts would still
render and the conclusion would be wrong. A metered API turns that into a
visible, bounded number.

The switch was also the moment to check a claim rather than inherit it: the
cold-start guarantee had been proven for `claude -p` only.

## Method

**Harness abstraction** (`boxlab/harness.py`). Both harnesses are descriptors —
auth variable, CLI, install script, process-match pattern, default model. Three
pieces of box-wheel scar tissue came across for pi, none of them incidental:

- pi needs Node ≥ 22.19 and boxes ship Node 20, so Node 22 is dropped rootlessly
  into `~/.local`; pi's own installer is interactive and bails without a TTY, so
  it installs via npm with `--ignore-scripts`.
- `npm install -g --prefix "$HOME/.local"` is load-bearing. Without it a box that
  already ships Node ≥ 22 falls through to the *system* npm, whose global prefix
  is root-owned; the install dies with EACCES leaving no `pi` and a silent
  zero-byte log at launch.
- **pi rewrites its process title to the bare word `pi`.** A launch-shaped
  `pgrep -f "pi -p"` never matches it. In box-wheel this made the liveness probe
  declare healthy agents dead and stop their boxes mid-mission. The match is now
  the ERE `(^|/)pi( |$)`, unit-tested against `pipewire` and `at-spi`.

**Credential isolation.** A box now receives exactly one harness auth variable —
its own. `OPENROUTER_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` are never both
present, and `ANTHROPIC_API_KEY` is still never written at all.

**Experiment driver** (`boxlab/experiment.py`). One thread per run:
create → provision → launch → cold-start cut → relaunch → budget end → harvest →
stop. Every timing decision comes from a **single wall clock started at the first
launch**, so a slow toolchain install cannot silently give one arm a shorter
working period. Box creation is staggered 8s because Box caps creation at 10/min.
Teardown is in a `finally`, with the box's TTL as a second backstop.

**Spend guard** (`boxlab/spend.py`). A **launch gate only** — it can refuse to
start a run, never stop one, because a mid-flight kill would truncate one arm and
bias the result exactly the way the harness switch was meant to avoid. An
unreadable OpenRouter status counts as exceeded: launching blind is how a budget
cap becomes decorative.

**Budget check before committing to the plan.** The per-key cap reads $100 with
$94.07 remaining, and the account $145.16 used of $195.00 purchased — about $50
of headroom, matching the Operator's figure. Noted for future readers: the
key-level `limit` is a per-key cap, **not** the account balance; a key can show
headroom while the account is empty, so `spend.probe()` reports both.

**Live smoke test**, arm C on pi, box `bx_ed4n2tv9`: create → provision (Node 22
+ pi + `uv tool install hypergraph-protocol`) → launch → run → kill → relaunch →
stop.

## Result

**SMOKE PASS on pi**, matching the Claude Code result exactly:

| Step | claude_code (`bx_rwjwxxs3`) | pi + deepseek-v4-pro (`bx_ed4n2tv9`) |
| --- | --- | --- |
| provision | ok | ok |
| mission ran, artifact written | yes | yes |
| kill + relaunch | `NO-PRIOR-SESSION` | `NO-PRIOR-SESSION` |
| boxes left running | 0 | 0 |

The cold-start guarantee therefore holds on **both** harnesses, which matters
more here than on Claude Code: pi ships `-c/--continue` and `-r/--resume` and
auto-saves every session, so a resumable transcript exists on disk. It is not
used because the launch never passes those flags — asserted for every
(arm, harness) pair by
`tests/test_boxlab.py::test_relaunch_is_a_genuine_cold_start`, and confirmed
empirically above.

**The measurement channel nearly disappeared, and the failure would have been
silent.** pi's `-p` mode writes only the final answer to its log — the entire
smoke run was **82 bytes**, no turns, no tool calls, no tokens, no cost. Claude
Code's `stream-json` had supplied all of that. Two of the four measures
(cold-start orientation cost, throughput and waste) had no source.

Recovered from pi's own docs: sessions **auto-save as JSONL trees** to
`~/.pi/agent/sessions/`, carrying the turn-by-turn transcript with tool calls,
tokens and cost. The harvest step now pulls that directory home as well. Had this
not been caught, nine three-hour runs would have completed, harvested, torn down
their boxes, and only at analysis time would it have emerged that the runs were
unmeasurable — with the evidence already deleted.

Tests: 96 pass (90 before). Checker: 0 violations.

**Cost so far: effectively zero.** Two smoke boxes, and OpenRouter key usage
unchanged at $5.93 after the pi run. That last figure is itself a caution — it
may mean OpenRouter's `usage` field lags, in which case the spend guard is
partially blind *during* a run and only reliable between runs. Not yet resolved.

**Known and accepted:** under pi, arm C runs **without** the skills layer.
`hypergraph skills install` writes into `.claude/skills`, which pi does not read,
so provisioning omits it for pi and the protocol arm has its primer and the
`hypergraph` CLI alone. This is a narrower test of arm C than the packaged
product offers, and it biases **against** arm C. Recorded in METRICS.md.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 70bc5b5bfa99af7043780da394810575fc98afe3

## State Impact

- target: NEW protocol-benchmark — M2 delivered and the harness changed by Operator directive: runs now use pi (pi.dev) on OpenRouter with deepseek/deepseek-v4-pro, all nine concurrent on a metered API, because a subscription quota wall would truncate arms unevenly and bias the result invisibly. Added boxlab/harness.py (both harnesses first-class), experiment.py (per-run wall clock, cold-start cut, harvest-before-teardown, staggered creation for Box's 10/min cap), spend.py (launch gate only — never kills a running arm), plus the shared mission and continuation prompts. Smoke PASSED on pi (box bx_ed4n2tv9): cold start returns NO-PRIOR-SESSION on BOTH harnesses, which matters more under pi because it ships -c/--continue and auto-saves sessions. Ready to run; 96 tests pass.
- target: NEW protocol-benchmark — measurement channel corrected before it cost a run: pi -p logs only the final answer (82 bytes for a whole smoke run), so cold-start orientation cost and throughput/waste had no source. Recovered via pi's session JSONL trees under ~/.pi/agent/sessions (turns, tool calls, tokens, cost), now included in the harvest with .env and the MCP bearer excluded at the source. Under pi, arm C runs WITHOUT the skills layer (.claude/skills is a Claude Code convention pi does not read) — a narrower test that biases against arm C, recorded in METRICS.md.
- target: blue-sun-8921 — negative knowledge for the backend/adapter surface: an agent harness's run log is not the same artifact as its session record, and the difference is silent. pi's print mode writes only the final answer while the full turn/token/cost tree auto-saves elsewhere on disk; a harvest scoped to the workspace would have destroyed the evidence at teardown and surfaced the loss only at analysis. Verify a measurement channel on a throwaway box before a run depends on it; scope: driving headless agent harnesses, confidence: high
