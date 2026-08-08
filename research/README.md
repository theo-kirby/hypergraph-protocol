# research/ — the protocol benchmark lab

**Nothing in this directory ships.** `hypergraph-protocol` publishes from two
explicit allow-lists in `pyproject.toml` (`[tool.hatch.build.targets.wheel]`'s
`force-include` and `[tool.hatch.build.targets.sdist]`'s `include`). Neither
mentions `research/`, so this tree stays out of the wheel and the sdist.
`tests/test_packaging.py` asserts that and fails if someone adds it.

That is deliberate. An end user installing the CLI has no use for Box drivers,
comparison harnesses, or chart code — it would be package weight and nothing else.

## What this is

The lab for the **protocol benchmark** — the experiment that asks whether the
Hypergraph protocol actually makes agent work better than plain git, rather than
merely working mechanically. Decision node: `southern-ridge-1802`.

Three isolated agents implement the **same paper** (word2vec, Mikolov et al.
2013, skip-gram with negative sampling on text8) on three identical Ascii Box
VMs. They share one prompt body and differ in exactly one section:

| Arm | Memory system |
| --- | --- |
| A (control) | git commits and files |
| B | Flywheel |
| C | Hypergraph protocol |

Four measures: reproduction fidelity, cold-start resilience, throughput and
waste, and a blind judge score.

## Layout

```
boxlab/       the Box driver — config, box_ctl, provision, runner
primers/      _core.md (identical for every arm) + memory/{git,flywheel,hypergraph}.md
```

## Provenance

`boxlab/` is a lean, Claude-only adaptation of **box-wheel**
(`~/box-wheel`), which solved this problem first and solved it properly. The
load-bearing lessons carried over verbatim, each learned the hard way there:

- Scripts are piped to `box ssh <id> bash -s` on **stdin**, never argv, so
  secrets never reach the box's process list.
- Claude authenticates with `CLAUDE_CODE_OAUTH_TOKEN` (the subscription).
  `ANTHROPIC_API_KEY` is **never** written to a box — it outranks the OAuth
  token and silently reroutes the run to API billing.
- A detached launch's ssh call usually **does not return**. That timeout is the
  successful launch, not a failure — so the agent is tracked *before* launching.
- `box new` reporting a READY state can precede the machine being ssh-able by a
  few seconds. A script fired into that gap returns `machine_not_running` and
  silently no-ops, which reads as a mission that ran and found nothing. Probe
  until the machine answers.
- `< /dev/null` on the detached launch is essential: it releases the ssh
  channel's stdin so the call can return at all.

## Requirements

The Box CLI, signed in (`box onboard`), plus credentials — see
`boxlab/config.py` for how they are resolved and what each arm needs.
