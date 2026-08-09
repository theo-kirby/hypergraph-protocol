---
node_id: 146f4371-f2d6-5d8d-a533-d866c1096c08
slug: staid-field-2723
title: 'Benchmark harness hardened: the first nine-run was not a controlled experiment'
created_at: '2026-08-09T09:38:10+00:00'
parents:
- ancient-dew-4488
summary: ''
---
## What

Hardened the benchmark harness so the second nine-run launch is a controlled
experiment, after a forensic pass over the first one's nine transcripts, the
GitHub account and the Flywheel account showed it was not.

Five phases, all landed and tested; the launch itself is not yet run.

- **Credentials.** `research/boxlab/redact.py` strips known secret values and
  secret-*shaped* runs (`sk-or-v1-`, `ghp_`, `github_pat_`, a long opaque value
  after an `_API_KEY=`, a bearer header), wired into `_harvest` so the rewrite
  happens **in memory between the base64 decode and the first write**. An archive
  that will not re-pack is discarded and logged, never written raw. The 16
  unpushed commits were rewritten to drop the transcripts and the redacted copies
  re-added; the `hg-viz` worktree's branch, which pointed at the old tip with zero
  unique commits, was reset onto the rewrite or it would have kept every leaked
  blob alive.

- **Isolation.** Repository names are now derived by the harness from
  (experiment, arm, seed) — `boxlab-w2v-hypergraph-s2` — so a collision is
  unreachable rather than detected. `publish-repo` takes no argument and rejects
  any, never force-pushes, and refuses to push into a repo whose committed
  `.boxlab-run` marker names a different run. Flywheel keys resolve per run
  (`FLYWHEEL_API_KEY_<ARM>_S<SEED>`); the shared fallback must be asked for.

- **Provisioning.** `flywheel setup` gains a skill flag so it stops exiting
  non-zero, and a failed install is now fatal. Arm C's two roots and a valid
  config are seeded by provisioning, so both protocol arms start from an
  initialised, empty memory system. `uv tool install` pins the version and the box
  asserts it.

- **The shipped CLI had two real defects.** `check --config <missing>` died with a
  raw `FileNotFoundError` traceback naming pathlib; it now fails with an
  instruction. A config declaring neither root passed silently while the checker
  guessed; it now warns. Added `--version`.

- **Publishing.** The helper's `.gitignore` covers venvs, build output, corpora
  and vector dumps, and a 50 MB gate excludes anything larger automatically,
  saying what it dropped.

- **Measurement.** METRICS.md gains a dated rev-1 section: dual fidelity
  (`final`, `best_recoverable`, and the gap between them), a pre-registered
  binary "produced a usable model at all", and cold-start eligibility gated on
  `had_prior_state` probed on the box at the cut.

`research/boxlab/preflight.py` is new: a pre-launch gate (credentials, Flywheel
isolation and account emptiness, nine repos reserved and verified empty, the
version pin, the primer invariants) plus an on-box assertion that runs after
provisioning and before the mission.

## Why

Follows `ancient-dew-4488`. That run's pre-registered verdict — no detectable
difference at n=3 — stands, because overlapping ranges mean "not detectable"
whatever the harness did. What it cannot support is anything stronger, and the
striking 0/3-vs-6/6 control pattern it reported is an artifact.

The forensics found four classes of defect, each of which corrupts the comparison
rather than merely losing a run:

1. **The arms were not isolated.** The primer told nine agents on one paper under
   one GitHub owner to "pick a descriptive kebab-case name". Three picked
   `word2vec-skipgram-text8`. Two force-pushed over it — hypergraph-s3's published
   work is gone — and flywheel-s1 answered a rejected push with
   `git fetch && git reset --hard FETCH_HEAD`, replacing its tree with a
   hypergraph arm's repo, graph and STATE.md included, then reading it. Twice. All
   three arm-B seeds shared one Flywheel account holding 458 nodes from unrelated
   past projects; one spent seven `get_node` calls reading a June FIFA World Cup
   campaign.

2. **Two of three arms ran with a broken memory system.** `flywheel setup --mode
   mcp --yes` exits non-zero — "Non-interactive setup requires one of
   --install-skill or --skip-skill" — so all three arm-B boxes had the HTTP MCP,
   no CLI and no contract doc, and spent their opening turns probing whether the
   tool was `flywheel_get_contract` or `flywheel_flywheel_get_contract`, `section`
   or `section_id`. Arm C had no scaffolding at all: hypergraph-s1 spent its
   entire second phase hand-rolling the protocol and never returned to training.

3. **Live keys leaked into git-tracked data.** Agents ran `cat ~/research/.env`
   thirty times across six of nine runs, because the primer handed them a
   `git push https://x-access-token:${GITHUB_TOKEN}@…` line.

4. **The fidelity measure sampled one instant.** It scored
   `artifacts/vectors.txt` at teardown only.

## Method

Forensics: read all 18 harvested session transcripts, queried the Flywheel MCP
(`flywheel_list_nodes owners:["me"]` → `total: 458`), and inspected the published
GitHub repos and the local commit graph.

Reproduced the `check` defect before fixing it, from hypergraph-s2's transcript:
entries 49-56 show `hypergraph export` succeeding, `check --config` dying in
`pathlib.read_text`, the agent reading `check --help`, then writing
`cat > .hypergraph/config.yml <<EOF backend: local EOF` and getting "0
violations". The plan attributed this to `check` forcing agents to *destroy* a
config; the transcript shows the config never existed, because the shipped CLI
has no `init` subcommand and the agent had hand-rolled `mkdir -p`.

Verification, all green except the two blocked on the Operator:

    uv run pytest tests/                      # 153 passed
    uv run tools/hypergraph.py check …        # 0 violations, 0 warnings
    git log -p --all -S 'sk-or-'              # only redact.py's own pattern
    uv run research/lab.py preflight --arms git flywheel hypergraph --seeds 3
                                              # 19/20; fails only on the missing keys

Redaction was validated against the real leak rather than a fixture: 46 findings
across 18 transcripts, 0 residual. An object-level scan of every blob reachable
from every ref now finds only `sk-ant-SHOULD-NEVER-APPEAR`, the deliberately-fake
test fixture.

The new analysis pipeline was validated against the first run's real data: it
recovers git-s2's published 23.29% against its 0.12% teardown artifact, and
correctly reports every arm's cold start as *not comparable*, because the old
runs carry no `had_prior_state` and under the new rule that data cannot support
the measure.

## Result

Harness hardened; the run not yet launched, blocked on the Operator.

- 153 tests pass, up from 128. New coverage: redaction and the standing
  no-secret-under-`research/runs` scan, repo-name assignment and the publish
  guards, per-run Flywheel isolation, arm-C seeding, the skill-layer symmetry
  rule, the two `check` defects, and every rev-1 measurement rule.
- Git history holds no real credential. Working tree clean by the same scan.
- Preflight reaches 19/20 against live GitHub and Flywheel, failing on exactly
  the one thing genuinely absent: the three per-run Flywheel keys.
- `*.c` is deliberately **not** git-ignored despite the plan calling for it. A
  hand-written `train.c` is the control arm's work; ignoring it would delete the
  evidence the repo exists to publish. `*.so`/`*.o` cover the build products, and
  the size gate covers the rest.
- The skill layer is now present or absent for **both** protocol arms together,
  per harness. Giving arm B a pi-readable Flywheel skill while arm C had none
  would have handed B a workflow layer C lacks — a new confound, in the
  protocol's favour, introduced by the fix for an old one.

Blocked on the Operator, and not started: rotation of the four exposed keys, and
three distinct Flywheel accounts. Nothing spends until both land.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e29fe30833cbe49ea0bd2950efe49d7f291048b7

## State Impact

- target: protocol-benchmark-4417 — the first nine-run benchmark is reclassified: its pre-registered verdict (no detectable difference at n=3) stands, but the run was NOT a controlled experiment and cannot support anything stronger. Arms reached each other (three runs shared one repo name, two force-pushed over it, one reset --hard onto another arm's tree and read its graph; all three arm-B seeds shared one 458-node Flywheel account). The 0/3-vs-6/6 control pattern recorded as a post-hoc observation in ancient-dew-4488 is now known to be a SAMPLING ARTIFACT: git-s1 reached 22.03% and git-s2 23.29% mid-run and published both, then overwrote the local artifact the measure sampled. The harness is hardened against all four defect classes and gated by research/boxlab/preflight.py, which refuses to launch on a shared Flywheel account, a taken repo name, a drifted primer or a version-pin mismatch. The relaunch is blocked on the Operator for key rotation and three distinct Flywheel accounts.
- target: protocol-benchmark-4417 — METRICS.md is re-pre-registered (rev-1, 2026-08-09, before the second launch and with no access to its data): fidelity is now two numbers, `final` and `best_recoverable` (the best model the run can point to, restricted to candidates whose number its own record cites within 0.5pp), with the gap between them a measure in its own right — how much proven work each memory system lost. "Produced a usable model at all" is pre-registered as a binary outcome so the 0/3-vs-6/6 pattern is a result if it recurs. Cold start now counts only runs that wrote something before the cut, with exclusions always reported. MIN_N=3 and the direction-aware overlap test are deliberately unchanged and now pinned by test.
- target: wandering-sun-8831 — two real defects in the shipped checker, found by watching agents fail against it rather than by review. `check --config <missing>` raised an unhandled FileNotFoundError from pathlib, naming the plumbing instead of the problem; two of three arm-C agents read that as "contents are wrong", wrote a one-line `backend: local` stub, and got "0 violations" because find_root had silently fallen back to guessing. Both fixed: a missing or unparseable config exits with an instruction naming the file, and an inferred root now warns when a config was supplied and declares none (warning, not violation — a single-root graph is legitimately unambiguous). `--version` added, which the benchmark's version pin and preflight both require.
- target: weathered-union-7494 — package version 0.0.2 → 0.0.3, carrying the two checker fixes and `--version`. tests/test_packaging.py holds `__version__` in step with pyproject, and the benchmark's arm-C boxes install `hypergraph-protocol==0.0.3` pinned and assert the installed version on the box, because `uv tool install` reuses a cached tool and would otherwise leave a box silently running an older build.
- target: NEW harness-hygiene — negative knowledge from running nine autonomous agents against live accounts. [scope: multi-agent experiment harnesses | confidence: high | evidence: this record] letting an agent name its own published artifact is a cross-contamination channel, not a convenience: nine agents on one paper under one owner produced three identical names, two force-pushes and one `reset --hard` onto a sibling's tree. Identifiers that must be unique across runs have to be assigned by the harness. [scope: provisioning autonomous agents | confidence: high | evidence: this record] a provisioning sentinel that fires when the script reaches its last line asserts nothing — `set -e` catches a command that fails and cannot catch one that succeeds at doing nothing; every arm needs a post-provision assertion that its memory system actually works. [scope: harvesting agent transcripts | confidence: high | evidence: this record] excluding a credentials file from a harvest does not contain credentials, because the agent prints them into the transcript, which is the one artifact the harvest cannot drop; redaction has to happen in memory before the first write.
