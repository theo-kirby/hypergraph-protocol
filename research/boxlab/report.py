"""Aggregate nine runs into the per-arm comparison METRICS.md asks for.

Deliberately conservative about what it will claim. With three seeds per arm the
honest summary is a median and a range, not a mean with a standard error, and
certainly not a ranking — so that is what this prints. `verdict()` refuses to
call a winner when the arms' ranges overlap, because at n=3 an overlapping range
is exactly the case where a difference is not detectable.

Fidelity comes from our own evaluator over each run's harvested `vectors.txt`
(never the arm's self-report — the pilot measured a 2.1-point overstatement from
an arm whose evaluator silently dropped 52% of the test set). The activity
measures come from the harness session transcripts.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional


# Minimum usable runs per arm before any comparison is made.
MIN_N = 3


def _median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _rng(values: List[float]) -> Optional[tuple]:
    return (min(values), max(values)) if values else None


def by_arm(run_reports: List[dict]) -> Dict[str, dict]:
    """Group per-run reports into per-arm summaries."""
    arms: Dict[str, List[dict]] = {}
    for report in run_reports:
        arms.setdefault(report.get("arm") or "?", []).append(report)

    summary: Dict[str, dict] = {}
    for arm, runs in sorted(arms.items()):
        # A diverged run produced NOTHING usable — averaging it in as 0% would
        # blend "trained badly" with "training blew up", which are different
        # findings. It is counted separately and excluded from the accuracy
        # statistics.
        diverged = sum(1 for r in runs
                       if (r.get("fidelity") or {}).get("diverged"))
        acc = [r["fidelity"]["total"]["accuracy"] for r in runs
               if r.get("fidelity") and not r["fidelity"].get("diverged")]
        cold = [r["cold_start"]["time_to_first_productive_s"] for r in runs
                if (r.get("cold_start") or {}).get(
                    "time_to_first_productive_s") is not None]
        orient = [r["cold_start"]["orientation_tool_calls"] for r in runs
                  if (r.get("cold_start") or {}).get(
                      "orientation_tool_calls") is not None]
        tools = [r["totals"]["tool_calls"] for r in runs]
        turns = [r["totals"]["assistant_turns"] for r in runs]
        cost = [r["totals"]["cost_usd"] for r in runs]
        summary[arm] = {
            "runs": len(runs),
            "produced_vectors": sum(1 for r in runs if r.get("fidelity")),
            "diverged": diverged,
            "usable_vectors": len(acc),
            "accuracy_median": _median(acc),
            "accuracy_range": _rng(acc),
            "accuracy_values": acc,
            "cold_start_s_median": _median(cold),
            "cold_start_s_range": _rng(cold),
            "orientation_calls_median": _median(orient),
            "tool_calls_median": _median(tools),
            "turns_median": _median(turns),
            "cost_usd_median": _median(cost),
        }
    return summary


# Which direction is "better" for each measure. Getting this wrong silently
# inverts a conclusion: an earlier version ranked every measure by highest
# median and announced the SLOWEST arm as the cold-start leader.
HIGHER_IS_BETTER = {
    "accuracy": True,
    "cold_start_s": False,       # seconds to first productive action
    "orientation_calls": False,  # calls spent before doing anything
    "cost_usd": False,
}


def verdict(summary: Dict[str, dict], key: str = "accuracy") -> str:
    """State what the data supports — including that it may support nothing.

    At three seeds per arm, overlapping ranges mean "not detectable at this
    sample size". Saying so is the result; picking the higher median anyway
    would be inventing one.
    """
    # An arm needs at least MIN_N usable runs before it can be compared at all.
    # Declaring a leader off two runs — as an earlier version did on partial
    # data — is not a result, it is a coin flip with a decimal point.
    ranges = {arm: s.get(f"{key}_range") for arm, s in summary.items()
              if s.get(f"{key}_range")
              and s.get("usable_vectors", s.get("runs", 0)) >= MIN_N}
    if len(ranges) < 2:
        thin = {a: s.get("usable_vectors", s.get("runs", 0))
                for a, s in summary.items()}
        return (f"{key}: not comparable — fewer than two arms have {MIN_N}+ "
                f"usable runs (usable per arm: {thin})")

    higher_better = HIGHER_IS_BETTER.get(key, True)
    ordered = sorted(
        ranges.items(),
        key=lambda kv: summary[kv[0]][f"{key}_median"],
        reverse=higher_better)
    best_arm, best_range = ordered[0]
    # Overlap test respects direction: for a lower-is-better measure the leader
    # is beaten if anyone's range reaches below its top.
    if higher_better:
        overlapping = [a for a, rng in ordered[1:] if rng[1] >= best_range[0]]
    else:
        overlapping = [a for a, rng in ordered[1:] if rng[0] <= best_range[1]]
    direction = "highest" if higher_better else "lowest"
    if overlapping:
        return (f"{key}: no detectable difference at n={MIN_N} — "
                f"{best_arm} has the {direction} median but its range overlaps "
                f"{', '.join(overlapping)}")
    return (f"{key}: {best_arm} leads ({direction} median "
            f"{summary[best_arm][f'{key}_median']:.4g}, no range overlap)")


def _fmt(value, spec: str = "") -> str:
    """Render a number, or a dash when the run did not produce one.

    A missing measure prints as `-`, never as 0 — an arm that produced nothing
    and an arm that scored zero are different findings.
    """
    if value is None:
        return "-"
    return format(value, spec) if spec else str(value)


def render(summary: Dict[str, dict]) -> str:
    header = (f"{'arm':<12} {'runs':>4} {'vec':>4} {'div':>4} {'accuracy':>10} "
              f"{'range':>16} {'cold-start s':>13} {'orient':>7} "
              f"{'tools':>6} {'cost$':>8}")
    lines = [header, "-" * len(header)]
    for arm, s in summary.items():
        rng = s["accuracy_range"]
        range_text = f"{rng[0]:.2%}-{rng[1]:.2%}" if rng else "-"
        lines.append(
            f"{arm:<12} {s['runs']:>4} {s['produced_vectors']:>4} "
            f"{s.get('diverged', 0):>4} "
            f"{_fmt(s['accuracy_median'], '.2%'):>10} "
            f"{range_text:>16} "
            f"{_fmt(s['cold_start_s_median'], '.0f'):>13} "
            f"{_fmt(s['orientation_calls_median'], '.0f'):>7} "
            f"{_fmt(s['tool_calls_median'], '.0f'):>6} "
            f"{_fmt(s['cost_usd_median'], '.3f'):>8}")
    lines.append("")
    lines.append(verdict(summary, "accuracy"))
    lines.append(verdict(summary, "cold_start_s"))
    return "\n".join(lines)
