# Measurement spec — frozen before any arm runs

This document is **pre-registered**. Every threshold, band, and rubric below was
fixed before the first measured run, and the literature reference numbers were
looked up before any arm existed. Changing anything here after data lands is a
new document with a new date, not an edit — a target chosen after seeing the
results is not a target.

Decision node: `southern-ridge-1802`.

## Revision, 2026-08-09 — re-pre-registered before the second nine-run launch

The first nine-run benchmark (2026-08-08) produced a defensible headline — *no
detectable difference at n=3* — and was **not a controlled experiment**. A
forensic pass over all nine transcripts, the GitHub account and the Flywheel
account found that arms could see and destroy each other's work, that two of
three arms were provisioned with a broken memory system, and that the fidelity
measure sampled one instant that happened to hide the control arm's real results.

The pre-registered verdict is unaffected: overlapping ranges at n=3 mean "not
detectable" whatever the harness did. What the run cannot support is anything
stronger — and in particular the striking 0/3-vs-6/6 control pattern is an
artifact of §1's sampling, not a finding.

Everything below stands as originally written except where marked **[rev-1]**.
Those changes are made **before** the second launch and with no access to its
data. Three of them (§1 dual fidelity, §1 binary outcome, §2 cold-start
eligibility) exist precisely because the first run showed the original measures
could be satisfied by a run that measured nothing.

The first run's data stays on record. It is not re-scored into this revision's
numbers, because a measure defined after seeing data is not pre-registered for
that data.

## The harness — a constant across arms, and what it costs us

Runs use **pi** (pi.dev) against **OpenRouter**, model
`deepseek/deepseek-v4-pro`, pinned explicitly. Chosen for cost: nine three-hour
missions on a metered API is a bounded, visible spend, where the same nine on a
subscription risks a quota wall mid-run — and a quota wall would truncate arms
unevenly and bias the comparison while the charts still rendered.

The harness is identical across arms, so the comparison stays internally valid.
Two consequences must be stated plainly in any write-up:

1. **The result is about this agent.** "The protocol helps *DeepSeek V4 Pro under
   pi*" does not automatically generalise to Claude Code. The Claude Code path is
   built and smoke-tested (`--harness claude_code`) precisely so the finding can
   be checked against a second agent later.
2. **Arm C runs without the skills layer.** `hypergraph skills install` writes
   Claude Code skills into `.claude/skills`, which pi does not read. Under pi the
   protocol arm has its primer and the `hypergraph` CLI and nothing else. That is
   a *narrower* test of arm C than the packaged product offers, and it biases
   against arm C rather than for it.

## Where the measurements come from

Not from the run log. pi's print mode writes only the final answer — 82 bytes for
an entire smoke run. The measurable record is pi's **session JSONL**, which it
auto-saves to `~/.pi/agent/sessions/` as a tree of entries carrying the
turn-by-turn transcript, the tool calls, and token and cost totals. The harvest
step pulls that directory home alongside the workspace; without it a run
completes and is simply unmeasurable.

Claude Code's equivalent is `--output-format stream-json --verbose`, whose
`result` event carries `num_turns`, `duration_ms`, `total_cost_usd` and full
token usage. Both are harvested, so either harness can be analysed the same way.

## The task given to every arm

Implement **word2vec** (Mikolov et al., 2013 — *Efficient Estimation of Word
Representations in Vector Space*), skip-gram with negative sampling, trained on
the **text8** corpus (17M words, ~71k vocabulary after a min-count of 5), and
evaluate it on the **Google analogy** (semantic–syntactic) test set.

Each arm must write its final vectors to `~/research/artifacts/vectors.txt` in
word2vec text format (first line `<vocab_size> <dim>`, then one
`word v1 v2 … vd` line per word). This is stated plainly in the mission and is
identical across arms.

## 1. Reproduction fidelity

**Measured by us, not by the arm.** We pull `vectors.txt` off each box and score
it with our own evaluator against our own copy of the analogy set. The arm never
sees the evaluator and never reports its own grade. An arm that grades itself is
measuring its optimism.

**Metric:** total accuracy on the Google analogy set, with the semantic and
syntactic subsets reported separately. Standard protocol: `a:b::c:d` answered by
nearest neighbour to `vec(b) - vec(a) + vec(c)` under cosine, excluding `a`, `b`,
and `c` from the candidates; questions with any out-of-vocabulary term are
skipped and the skip count is reported.

**Literature reference band** — vanilla SGNS on text8, Google analogy total
accuracy, from *On SkipGram Word Embedding Models with Negative Sampling*
(arXiv:2009.04413v2, Tables IX / XII / XIII; window 10, k=1, 20 epochs):

| dim | semantic | syntactic | **total** |
| --- | --- | --- | --- |
| 50  | — | — | 18.60% |
| 100 | 20.50% | 26.77% | **24.16%** |
| 200 | — | — | 27.13% |

Those runs use `k=1`, which is unusually few negative samples; the paper's own
recommended setting (k=10, 20 epochs) does better. The band is therefore
**conservative** — a competent implementation should reach it, not strain for it.

**Scoring:**

- `reproduced` — total accuracy ≥ **20%** at dim ≥ 100.
- `matched-literature` — total accuracy ≥ **24.16%** at dim ≥ 100.
- The raw number is reported regardless of band, always, including 0.

Dimension and epoch count are recorded but not constrained. An arm that reaches
the band with fewer epochs did better, and the throughput measure will say so.

### **[rev-1]** Two fidelity numbers, not one

The original measure scored `artifacts/vectors.txt` **as it stood at teardown**,
and nothing else. That is one sample of a moving quantity, and on the first run
it sampled the wrong instant: git-s1 reached 22.03% and git-s2 23.29% mid-run,
both published those vectors to GitHub, and both then overwrote the local file
with a diverged run. `boxwheel/word2vec-cpu-baseline` still holds git-s2's
`vectors.txt.xz`. The reported "control produced 0/3 usable models" is that
sampling artifact, not a property of the control arm.

Both of these are now pre-registered:

- **`fidelity_final`** — the original measure, unchanged: our evaluator over
  `artifacts/vectors.txt` at teardown. *What the run left behind.*
- **`fidelity_best_recoverable`** — the best model the run can still **point
  to**. Every `vectors*` dump in the harvest and in the run's published
  repository is scored, and the maximum is taken **over those whose number the
  run's own record cites**.

  "Cites" is mechanical, not a judgement call: the run's README, `NOTES.md`,
  `DECISIONS.md`, `DEAD-ENDS.md`, `STATE.md`, `results.json`, its record- and
  state-graph node files, and its commit messages are scanned for accuracy
  figures (`23.29%` or `accuracy: 0.2329`), and a scored candidate qualifies if
  a cited figure lands within **0.5 percentage points** of it.

  A higher-scoring file the run never mentions **does not count**. It is not
  recovered knowledge, it is luck, and counting it would measure the harvest
  rather than the memory system — which is the mistake this revision exists to
  stop making.

- **The gap**, `fidelity_best_recoverable − fidelity_final`, is itself a
  pre-registered measure. It is **how much proven work each memory system lost**.
  Lower is better; zero is the ideal. It is reported as `null`, never as zero,
  when either side is absent — a gap between a number and a non-number is not a
  gap of nothing.

### **[rev-1]** Produced a usable model at all — a binary outcome

Declared in advance so that a 0/3-vs-6/6 pattern, if it recurs, is a **result**
rather than something noticed afterwards. Two counts per arm:

- **left behind** — runs whose teardown artifact is non-diverged and scoreable.
- **can point to** — runs that additionally cite their own number, i.e. runs with
  a `fidelity_best_recoverable`.

The second is never larger than the first. A model whose score the run never
wrote down is one its memory system did not preserve, and that is the thing
under test.

**Known risk, recorded in advance:** 20 epochs over 17M words on 4 vCPU is not
free. A pure-Python inner loop will not finish; a vectorised or compiled one
will. Failing on that is a legitimate outcome, not a broken experiment — but if
*every* arm fails on it, the run measures engineering throughput and says
nothing about memory systems, and we report it that way.

## 2. Cold-start resilience

The measure the protocol actually claims, and the reason this experiment exists.

**Mechanism.** Each `claude -p` invocation is a fresh session — `runner.py` never
passes `--resume` or `--continue`, so a relaunch carries **no conversation
history**. Killing the mission and relaunching leaves only the box's filesystem,
which is exactly the memory system under test.
`tests/test_boxlab.py::test_relaunch_is_a_genuine_cold_start` holds that
property. The live smoke test verifies it empirically on a real box.

**Protocol.** At the midpoint of the budget, `kill_mission()`, then relaunch with
a **continuation prompt identical across arms**: it says the previous session
ended, and to pick the work up. It names no file, no tool, and no memory system.

**Metrics**, all read from the stream-json log of the second session:

- **time-to-first-productive-action** — wall-clock from launch to the first tool
  call that advances the work, as opposed to reading, listing, or searching.
- **orientation cost** — number of tool calls, and tokens, before that moment.
- **rediscovery** — did the second session repeat work the first had already
  finished or already refuted? Counted by hand against the first session's log,
  and the count is the headline number of this measure.
- **continuity** — did it resume the live thread, or start something unrelated?

### **[rev-1]** Eligibility: the cut only counts if there was state to recover

A cold-start measurement over a run that wrote nothing before the cut measures
nothing. It cannot: there is no prior state, so "recovering it" is vacuous, and
the number it produces is indistinguishable from a fast cold start.

On the first run this was not a hypothetical. Only **one** of three arm-B seeds
wrote to Flywheel before the cut; the other two wrote nothing and were scored on
recovering it anyway. The one seed that *did* have six prior nodes failed to find
them and rebuilt a complete duplicate tree — root, four experiments, and a
synthesis, twice. That is the finding this measure exists to catch, and two
vacuous runs diluted it into invisibility.

So the driver records **`had_prior_state`** per run, probed on the box **at the
cut, before the kill**, per arm:

| arm | prior state means |
| --- | --- |
| git | ≥ 1 commit in `~/research` |
| flywheel | ≥ 1 node in **this run's** Flywheel account |
| hypergraph | ≥ 1 record node beyond the provisioned root |

Runs where `had_prior_state` is not `True` are **excluded** from the cold-start
statistic, and **the exclusion count and the excluded run ids are reported
alongside it, always**. `None` — the probe failed — excludes as well: unknown is
not the same as no, and must not be scored as either.

An arm needs `MIN_N` *eligible* runs before its cold-start figure is compared at
all, on the same rule as every other measure. An arm that excludes its way below
that reports "not comparable", which is the honest reading.

## 3. Throughput and waste

From the stream-json logs, both sessions, per arm:

- **work units per hour** — commits for the control, nodes for B and C, plus a
  common denominator: distinct experiments run.
- **tokens** and **`total_cost_usd`** — read from the final result event.
- **waste** — turns spent re-deriving something already established in the same
  run, plus turns spent on an approach the run had already refuted.
- **overhead** — turns spent operating the memory system itself. This is the
  cost side of the ledger, and B and C are expected to pay more of it than A.
  If the protocol arms win, this number is what they paid to win.

## 4. Blind judge

A separate model reads each final repository with the arm identity and all
memory-system artifacts stripped, and scores it against a fixed rubric:

| Axis | Question |
| --- | --- |
| TRUE | Are the claims supported by the recorded evidence? |
| REPRODUCIBLE | Could a stranger re-run this and get these numbers? |
| HONEST | Are failures, dead ends, and uncertainty recorded? |
| LEGIBLE | Can a newcomer tell what happened and why? |
| COMPLETE | Is the work finished, or abandoned mid-thread? |

Five axes, 1–5 each. The judge sees the repository only — never the logs, never
the arm name, never this document.

## Design constraints held across all four measures

- **Arms differ only in their memory section.** `_core.md` and the mission are
  byte-identical; the three memory sections are held to within 15% word count by
  test. Prompt bulk is not allowed to become the independent variable.
- **Seeds: 3 per arm, 9 runs.** One run per arm is an anecdote — agent-run
  variance is large, and at ~$0.036/hour per box the repeats are nearly free.
- **`MIN_N = 3` and the direction-aware overlap test are unchanged.** Both were
  correct on the first run and are deliberately not touched: at three seeds an
  overlapping range means "not detectable at this sample size", and saying so is
  the result. Picking the higher median anyway would invent one. The direction
  table matters as much — an earlier version ranked every measure by highest
  median and announced the *slowest* arm as the cold-start leader.
- **[rev-1] The arms must be unable to reach each other.** On the first run they
  were not: three runs published to the same repository under one GitHub owner,
  two force-pushed over it, one `reset --hard`ed onto another arm's tree and read
  its graph, and all three arm-B seeds shared one Flywheel account holding 458
  nodes from unrelated projects. Repository names are now assigned by the harness
  from (experiment, arm, seed), the publish helper takes no argument and never
  force-pushes, and each arm-B seed gets its own Flywheel account, verified empty
  before launch. `research/boxlab/preflight.py` refuses to launch otherwise.
- **[rev-1] Both protocol arms get their skill layer, or neither does.** The
  Flywheel skill and the hypergraph skills bundle are both host-agent conventions
  that pi does not read. Under pi neither arm gets one; under Claude Code both
  do. Installing one and not the other would hand that arm a workflow layer its
  counterpart lacks, and the run would measure that instead.
- **[rev-1] Both protocol arms start from an initialised, empty memory system.**
  A Flywheel account with zero nodes still accepts a write, so arm B's first act
  could be to record work. A `.hypergraph/` that does not exist accepts nothing,
  and on the first run arm C's setup consumed hypergraph-s1's entire second
  phase. Provisioning now seeds arm C's two roots and a valid config — roots
  only, since arm B is handed no skeleton either.
- **The control is a real control.** Arm A is taught commit-as-record, a running
  `NOTES.md` / `DECISIONS.md` / `DEAD-ENDS.md`, branch-per-alternative, and log
  interrogation. If a protocol cannot beat competent git hygiene, that is the
  finding, and we publish it.
- **Negative results ship.** If the arms are indistinguishable, that is the
  result and it goes in the record graph with the same care as any other.
