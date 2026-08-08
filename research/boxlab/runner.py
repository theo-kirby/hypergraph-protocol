"""Launch and watch a headless Claude Code mission on a box, detached.

Adapted from box-wheel's `research/runners/_common.py` + `claude_code.py`.
`build_launch_script` is pure; everything else is thin I/O over `box ssh`.

Three details are load-bearing, all of them box-wheel's scar tissue:

- **`< /dev/null` on the launch.** It releases the ssh channel's stdin so the
  call can return. Without it the channel stays open and the launch hangs.
- **`nohup setsid`.** Keeps the mission alive after the ssh session closes.
- **A launch-ssh timeout is SUCCESS, not failure.** `box ssh` frequently does not
  return after backgrounding. Callers must therefore record the run *before*
  launching, or a successful launch looks like a lost agent.

A fourth detail is specific to this experiment. Each `claude -p` invocation is a
**fresh session** — headless print mode keeps no conversation history unless
`--resume`/`--continue` is passed, and this module never passes them. So
`kill_mission()` followed by `launch()` is a **genuine cold start**: the only
continuity across it is the box's filesystem, which is precisely the memory
system under test. That is the mechanism for the cold-start-resilience measure,
and it costs nothing to arrange.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .arms import Arm
from .box_ctl import BoxController, still_booting
from .provision import RESEARCH_DIR

# Keep the launch wait short: we expect it not to return.
LAUNCH_TIMEOUT_S = 45.0

# `pgrep -f` / `pkill -f` pattern matching the mission process.
PROCESS_MATCH = "claude -p"


def log_path(run_id: str) -> str:
    return f"{RESEARCH_DIR}/runs/{run_id}.log"


def build_launch_script(run_id: str, mission: str, arm: Arm, *,
                        model: Optional[str] = None) -> str:
    """The detached headless-Claude launch bash (pure — no side effects).

    Sources the box's `.env` so `CLAUDE_CODE_OAUTH_TOKEN` (the subscription) and
    `GITHUB_TOKEN` are present, then launches under `nohup setsid` with
    stream-json captured to `runs/<run_id>.log`. The MCP config is wired only for
    the arm that has one — the control must not be handed a tool it was never
    told about.
    """
    q = shlex.quote(mission or "")
    log = log_path(run_id)
    mcp = "--mcp-config .mcp.json " if arm.needs_flywheel_mcp else ""
    model_flag = f"--model {shlex.quote(model)} " if model else ""
    return (
        f"cd {RESEARCH_DIR} && "
        f'export PATH="$HOME/.local/bin:$HOME/.flywheel/bin:$PATH" && '
        f"set -a && . ./.env && set +a && "
        f"nohup setsid claude -p {q} "
        f"--output-format stream-json --verbose "
        f"--dangerously-skip-permissions "
        f"{model_flag}{mcp}"
        f"< /dev/null > {log} 2>&1 &\n"
        f'echo "launched {run_id} pid $!"\n'
    )


@dataclass
class RunHandle:
    """What we know about one launched mission. State is reconciled, not trusted."""

    run_id: str
    box_id: str
    arm: str
    seed: int = 0
    state: str = "running"
    started_at: float = field(default_factory=time.time)
    last_activity: str = ""
    launches: int = 1  # incremented by each cold-start relaunch

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id, "box_id": self.box_id, "arm": self.arm,
            "seed": self.seed, "state": self.state,
            "started_at": self.started_at, "last_activity": self.last_activity,
            "launches": self.launches,
        }


def launch(box_id: str, run_id: str, mission: str, arm: Arm, *,
           model: Optional[str] = None,
           box: Optional[BoxController] = None) -> Tuple[bool, str]:
    """Start the mission detached. Returns `(launched, note)`.

    A `TimeoutExpired` is reported as launched — see the module docstring. A
    `machine_not_running` result with rc 0 is NOT: that is the silent no-op where
    the mission never ran, and it must be loud.
    """
    ctl = box or BoxController()
    script = build_launch_script(run_id, mission, arm, model=model)
    try:
        rc, out = ctl.ssh_exec(box_id, script, timeout=LAUNCH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return True, "launched (detached; ssh did not return)"
    if still_booting(out):
        return False, "machine not running — the mission never started"
    if rc != 0:
        return False, f"launch failed (rc={rc}): {out[-500:]}"
    return True, "launched (detached)"


def is_alive(box_id: str, *, box: Optional[BoxController] = None) -> Optional[bool]:
    """True/False if the mission process is running; None if the probe failed."""
    ctl = box or BoxController()
    probe = (f"if pgrep -f {shlex.quote(PROCESS_MATCH)} >/dev/null 2>&1; "
             "then echo ALIVE; else echo DEAD; fi\n")
    try:
        _, out = ctl.ssh_exec(box_id, probe, timeout=60.0)
    except Exception:
        return None
    if "ALIVE" in out:
        return True
    if "DEAD" in out:
        return False
    return None


def tail(box_id: str, run_id: str, *, lines: int = 40,
         box: Optional[BoxController] = None) -> str:
    """The last `lines` of the run's raw stream-json log."""
    ctl = box or BoxController()
    _, out = ctl.ssh_exec(
        box_id, f"tail -n {int(lines)} {log_path(run_id)} 2>/dev/null || true\n",
        timeout=90.0)
    return out


def fetch_log(box_id: str, run_id: str, *,
              box: Optional[BoxController] = None) -> str:
    """The whole stream-json log, framed so ssh banners can be stripped.

    The log is the primary measurement channel — turn boundaries, tool calls,
    token counts and `total_cost_usd` all live in it — so it comes back whole
    rather than tailed. Sentinel framing beats trusting that the transport added
    nothing of its own.
    """
    ctl = box or BoxController()
    start, end = "__BOXLAB_LOG_START__", "__BOXLAB_LOG_END__"
    _, out = ctl.ssh_exec(
        box_id,
        f"echo {start}\ncat {log_path(run_id)} 2>/dev/null || true\necho {end}\n",
        timeout=300.0)
    if start in out and end in out:
        return out.split(start, 1)[1].rsplit(end, 1)[0].lstrip("\n")
    return out


def kill_mission(box_id: str, *, box: Optional[BoxController] = None) -> bool:
    """Kill the mission process, leaving the box and its filesystem intact.

    This is the cold-start intervention: the session dies, the work on disk
    survives, and the next `launch()` starts with no conversation history.
    """
    ctl = box or BoxController()
    try:
        ctl.ssh_exec(box_id, f"pkill -f {shlex.quote(PROCESS_MATCH)} || true\n",
                     timeout=60.0)
    except Exception:
        return False
    for _ in range(10):
        if is_alive(box_id, box=ctl) is False:
            return True
        time.sleep(2.0)
    return False
