"""Turn a harvested run into the numbers METRICS.md asks for.

Reads a harness session transcript and produces per-run measures: turns, tool
calls, tokens, cost, and the cold-start timings. Handles both transcript shapes,
because the run may have used either harness:

- **pi** — `~/.pi/agent/sessions/**/**.jsonl`, a tree of entries keyed by
  `id`/`parentId`, each with a `timestamp`. Assistant entries carry
  `message.usage` with `input`/`output`/`reasoning`/`totalTokens`.
- **Claude Code** — `--output-format stream-json`, whose final `result` event
  carries `num_turns`, `duration_ms`, `total_cost_usd` and full token usage.

**Cost is computed here, not read.** pi reports `usage.cost.total = 0` for a
custom OpenRouter provider — it has no pricing table for one — so a run that
trusted that field would report every arm as free. OpenRouter's own per-key
`usage` is authoritative but account-wide, and nine concurrent runs share one
key, so it cannot attribute cost to a run either. Pricing the token counts from a
pinned table is the only per-run figure that is both exact and attributable.

The *productive action* heuristic decides the headline cold-start number, so it
is stated explicitly rather than buried: reading, listing and searching are
orientation; writing, editing, and any other command is work. Both a strict and a
loose reading are reported so a sceptical reader can see whether the conclusion
depends on where the line was drawn.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# OpenRouter list prices, USD per token, pinned 2026-08-08. Recorded rather than
# fetched so a re-analysis months later reproduces the same figures.
PRICING: Dict[str, Dict[str, float]] = {
    "deepseek/deepseek-v4-pro": {"input": 0.000000435, "output": 0.00000087},
    "deepseek/deepseek-v4-flash": {"input": 0.00000014, "output": 0.00000028},
}

# Tools that only look at the world. Everything else changes it.
READ_ONLY_TOOLS = {"read", "list", "ls", "glob", "grep", "find", "search"}

# A bash command is orientation if it only inspects. Anchored so `catalogue` or
# `lsof` cannot pass as `cat` or `ls`.
READ_ONLY_BASH = re.compile(
    r"^\s*(ls|cat|head|tail|pwd|find|grep|wc|file|stat|du|df|which|echo|env|"
    r"tree|less|more|test|ps|nvidia-smi|uptime|"
    r"git\s+(log|status|diff|show|branch|remote))\b")

# MCP tool names that READ the graph. Calling these is orienting, not working —
# and counting them as work made the Flywheel arm look instantly productive when
# it was reading its own notes.
READ_ONLY_MCP = re.compile(
    r"(get|list|read|search|find|tree|parents|children|status|contract|export)",
    re.IGNORECASE)


def _split_chain(command: str):
    """Split a shell chain into its parts, dropping pure navigation.

    `cd ~/research && git log` is orientation, but a naive prefix match sees
    `cd` and calls it work. Leading `cd`/`export`/`source` segments carry no
    information about intent, so they are dropped and the rest is judged.
    """
    parts = re.split(r"&&|\|\||;|\|", command)
    kept = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if re.match(r"^(cd|export|source|\.)\b", stripped):
            continue
        kept.append(stripped)
    return kept


def is_orientation_bash(command: str) -> bool:
    """True if every meaningful segment of the chain only inspects."""
    segments = _split_chain(command)
    if not segments:
        return True  # pure `cd` — navigation, not work
    return all(READ_ONLY_BASH.match(s) for s in segments)


def is_orientation_tool(name: str, bash_commands) -> bool:
    """True if this tool call reads rather than changes anything."""
    low = (name or "").lower()
    if low in READ_ONLY_TOOLS:
        return True
    if low.startswith("mcp") or "flywheel" in low:
        return bool(READ_ONLY_MCP.search(low)) or low in {"mcp"}
    if low == "bash":
        return all(is_orientation_bash(c) for c in bash_commands) if bash_commands else True
    return False


@dataclass
class Turn:
    """One assistant turn: when it happened, what it did, what it cost."""

    timestamp: float
    tools: List[str] = field(default_factory=list)
    bash_commands: List[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read: int = 0


@dataclass
class SessionMetrics:
    harness: str = ""
    model: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    turns: List[Turn] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def tool_calls(self) -> int:
        return sum(len(t.tools) for t in self.turns)

    def tokens(self) -> Dict[str, int]:
        return {
            "input": sum(t.input_tokens for t in self.turns),
            "output": sum(t.output_tokens for t in self.turns),
            "reasoning": sum(t.reasoning_tokens for t in self.turns),
            "cache_read": sum(t.cache_read for t in self.turns),
        }

    def cost_usd(self) -> Optional[float]:
        """Priced from the pinned table. None when the model is unknown."""
        price = PRICING.get(self.model)
        if price is None:
            return None
        tok = self.tokens()
        # Reasoning tokens bill as output on OpenRouter, and they are not
        # included in `output` — counting only `output` understates a reasoning
        # model's cost, sometimes by a lot.
        return (tok["input"] * price["input"]
                + (tok["output"] + tok["reasoning"]) * price["output"])

    def first_productive(self, *, strict: bool) -> Optional[float]:
        """Seconds from session start to the first turn that changes something.

        `strict` counts only unambiguous mutation (a write/edit tool, or a bash
        command that is not a known inspector). The loose reading counts any tool
        call at all, which is the most generous possible view of orientation
        cost.
        """
        for turn in self.turns:
            if not turn.tools:
                continue
            if not strict:
                return turn.timestamp - self.started_at
            for name in turn.tools:
                if not is_orientation_tool(name, turn.bash_commands):
                    return turn.timestamp - self.started_at
        return None

    def to_dict(self) -> dict:
        return {
            "harness": self.harness, "model": self.model,
            "duration_s": round(self.duration_s, 1),
            "assistant_turns": len(self.turns),
            "tool_calls": self.tool_calls,
            "tokens": self.tokens(),
            "cost_usd": self.cost_usd(),
            "time_to_first_productive_s": self.first_productive(strict=True),
            "time_to_first_tool_s": self.first_productive(strict=False),
        }


def _iso(value) -> float:
    if isinstance(value, (int, float)):
        return float(value) / (1000.0 if value > 1e11 else 1.0)
    if isinstance(value, str):
        from datetime import datetime
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def parse_pi_session(path: Path) -> SessionMetrics:
    metrics = SessionMetrics(harness="pi")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        stamp = _iso(entry.get("timestamp"))
        if stamp:
            metrics.started_at = metrics.started_at or stamp
            metrics.ended_at = max(metrics.ended_at, stamp)
        if entry.get("type") == "model_change":
            metrics.model = entry.get("modelId") or metrics.model
        message = entry.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        turn = Turn(timestamp=stamp)
        usage = message.get("usage") or {}
        turn.input_tokens = int(usage.get("input") or 0)
        turn.output_tokens = int(usage.get("output") or 0)
        turn.reasoning_tokens = int(usage.get("reasoning") or 0)
        turn.cache_read = int(usage.get("cacheRead") or 0)
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                name = block.get("name") or "?"
                turn.tools.append(name)
                if name == "bash":
                    args = block.get("arguments") or {}
                    if isinstance(args, dict) and args.get("command"):
                        turn.bash_commands.append(str(args["command"]))
        metrics.turns.append(turn)
    return metrics


def parse_claude_stream(path: Path) -> SessionMetrics:
    metrics = SessionMetrics(harness="claude_code")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") == "result":
            duration = float(entry.get("duration_ms") or 0) / 1000.0
            metrics.ended_at = metrics.started_at + duration
            usage = entry.get("usage") or {}
            metrics.turns.append(Turn(
                timestamp=metrics.started_at,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                cache_read=int(usage.get("cache_read_input_tokens") or 0),
            ))
            continue
        message = entry.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        turn = Turn(timestamp=metrics.ended_at or metrics.started_at)
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                turn.tools.append(block.get("name") or "?")
                inp = block.get("input") or {}
                if isinstance(inp, dict) and inp.get("command"):
                    turn.bash_commands.append(str(inp["command"]))
        if turn.tools:
            metrics.turns.append(turn)
    return metrics


def find_pi_sessions(run_dir: Path) -> List[Path]:
    """Session files inside a harvested workspace, oldest first.

    Phase 1 and phase 2 are separate sessions in the same directory, and their
    order is the cold-start boundary — so they are sorted by name, which pi
    stamps with the session start time.
    """
    root = run_dir / ".pi" / "agent" / "sessions"
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.jsonl"))


def analyse_run(run_dir: Path) -> dict:
    """Per-run report: each phase, plus the cold-start comparison between them."""
    sessions = [parse_pi_session(p) for p in find_pi_sessions(run_dir)]
    if not sessions:
        for name in ("phase1.log", "phase2.log"):
            path = run_dir / name
            if path.is_file() and path.stat().st_size > 0:
                sessions.append(parse_claude_stream(path))

    report = {
        "run": run_dir.name,
        "phases": [s.to_dict() for s in sessions],
    }
    if len(sessions) >= 2:
        before, after = sessions[0], sessions[-1]
        report["cold_start"] = {
            "time_to_first_productive_s": after.first_productive(strict=True),
            "time_to_first_tool_s": after.first_productive(strict=False),
            "orientation_tool_calls": _orientation_calls(after),
            "phase1_tool_calls": before.tool_calls,
            "phase2_tool_calls": after.tool_calls,
        }
    totals = {
        "assistant_turns": sum(len(s.turns) for s in sessions),
        "tool_calls": sum(s.tool_calls for s in sessions),
        "cost_usd": sum((s.cost_usd() or 0.0) for s in sessions),
    }
    report["totals"] = totals
    return report


def _orientation_calls(session: SessionMetrics) -> Optional[int]:
    """Tool calls spent before the first productive one (the cold-start tax)."""
    count = 0
    for turn in session.turns:
        for name in turn.tools:
            if not is_orientation_tool(name, turn.bash_commands):
                return count
            count += 1
    return None


# ---- dual fidelity: what the run produced vs what it can still point to -------
#
# The nine-run benchmark scored one file, `artifacts/vectors.txt`, as it stood at
# teardown, and reported that the control arm produced 0/3 usable models. That
# was a sampling artifact. git-s1 reached 22.03% and git-s2 23.29% mid-run and
# published both to GitHub; both then overwrote the artifact with a diverged
# run, and the harvest sampled the wreckage. `boxwheel/word2vec-cpu-baseline`
# still holds git-s2's vectors.
#
# So two numbers, both pre-registered (METRICS.md §1):
#
#   fidelity_final            — the artifact at teardown. What the run left behind.
#   fidelity_best_recoverable — the best model the run can still POINT TO from its
#                               own record and published repo.
#
# The second has a deliberately awkward constraint: a candidate counts only if the
# run's own record cites its number. A better file sitting in a directory the run
# never mentions is not recovered knowledge, it is luck, and counting it would
# measure the harvest rather than the memory system. The gap between the two is
# itself the measure — it is how much proven work each memory system lost.

# A number in a record is "the same result" as a scored candidate if it lands
# within this many percentage points. Wide enough for rounding and for a run that
# reported 23.3 against a scored 23.29; far tighter than the spread between any
# two genuinely different training runs.
CITATION_TOLERANCE_PP = 0.5

# Percentages as a run writes them: `23.29%`, `accuracy: 0.2329`, `22.0 %`.
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_FRACTION = re.compile(
    r"(?:accuracy|acc|total|score)\D{0,12}?(0\.\d{2,6})\b", re.IGNORECASE)


def cited_accuracies(text: str) -> List[float]:
    """Every accuracy a record claims, as fractions in [0, 1].

    Both notations, because arms write both. Values outside a plausible analogy
    range are dropped: `100%` of something else, or a `0.95` learning-rate decay,
    are not claims about this measure.
    """
    found: List[float] = []
    for match in _PERCENT.finditer(text or ""):
        value = float(match.group(1)) / 100.0
        if 0.0 < value <= 0.75:
            found.append(value)
    for match in _FRACTION.finditer(text or ""):
        value = float(match.group(1))
        if 0.0 < value <= 0.75:
            found.append(value)
    return found


def record_text(run_dir: Path, extra: Optional[List[Path]] = None) -> str:
    """Everything this run offers as its own account of itself.

    The memory-system artifacts of all three arms, plus the published README and
    the structured results. Deliberately arm-agnostic: the question is "can this
    run point to the number", and each arm answers it in its own medium.
    """
    names = ("README.md", "NOTES.md", "DECISIONS.md", "DEAD-ENDS.md",
             "STATE.md", "results.json", "COMMITS.txt")
    parts: List[str] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in names or (".hypergraph/graph" in str(path)
                                  and path.suffix == ".md"):
            try:
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    for path in extra or []:
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def find_vector_candidates(root: Path) -> List[Path]:
    """Every scoreable vector dump under `root`, final artifact first.

    `artifacts/vectors.txt` leads because it is `fidelity_final`'s subject and
    the two measures should agree about which file that is.
    """
    seen: List[Path] = []
    for path in sorted(root.rglob("vectors*")):
        if not path.is_file() or path.stat().st_size < 1024:
            continue
        if path.suffix in (".gz", ".xz", ".bz2", ".zip"):
            continue  # compressed dumps are decompressed by the caller, if at all
        seen.append(path)
    seen.sort(key=lambda p: (not str(p).endswith("artifacts/vectors.txt"), str(p)))
    return seen


def best_recoverable(scored: List[dict], cited: List[float],
                     *, tolerance_pp: float = CITATION_TOLERANCE_PP) -> Optional[dict]:
    """The best-scoring candidate whose number the run's own record cites.

    Returns the scoring dict augmented with `cited: bool` and `source`, or None
    when the run can point to nothing. A run whose record cites no number at all
    recovers nothing by this measure, which is the intended reading: an
    unciteable artifact is not a result the memory system preserved.
    """
    tolerance = tolerance_pp / 100.0
    eligible = []
    for entry in scored:
        if entry.get("diverged"):
            continue
        accuracy = (entry.get("total") or {}).get("accuracy")
        if accuracy is None:
            continue
        if any(abs(accuracy - claim) <= tolerance for claim in cited):
            eligible.append((accuracy, entry))
    if not eligible:
        return None
    eligible.sort(key=lambda pair: pair[0], reverse=True)
    best = dict(eligible[0][1])
    best["cited"] = True
    return best


def fidelity_gap(final: Optional[dict], recoverable: Optional[dict]
                 ) -> Optional[float]:
    """`best_recoverable - final`, in accuracy points. The work the run lost.

    None when either side is absent — a gap between a number and a non-number is
    not zero, and reporting it as zero would say a run lost nothing when what
    actually happened is that it produced nothing.
    """
    def acc(entry):
        if not entry or entry.get("diverged"):
            return None
        return (entry.get("total") or {}).get("accuracy")

    a, b = acc(final), acc(recoverable)
    if a is None or b is None:
        return None
    return b - a
