"""Box lifecycle + the ssh-on-stdin primitive — the only place this lab mutates.

Adapted from box-wheel's `control/box_ctl.py`, trimmed to what the benchmark
needs and carrying its two hard-won boot lessons intact:

- `box --json` may emit **JSONL** (`box new` streams provisioning steps), so the
  final box object is the last line carrying an id — not `json.loads(stdout)`.
- `box new` returning a READY state can precede the machine being ssh-able by a
  few seconds. A script fired into that gap comes back `machine_not_running`
  with **rc 0** and silently does nothing. That failure is invisible later: the
  box looks provisioned, the mission never ran, and the run reads as an agent
  that did no work. `await_ssh_ready` closes the gap; `still_booting` lets
  callers detect it if it slips through anyway.

Scripts always travel on **stdin** (`box ssh <id> bash -s`), never argv, so the
secrets inside them never appear in the box's process list.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

# Box states that mean "up and ssh-able".
READY_STATES = frozenset({"ready", "running", "idle"})
CREATE_TIMEOUT_S = 120.0
CREATE_POLL_S = 3.0

# The sentinel a too-early ssh returns, and the bounded probe that waits it out.
MACHINE_NOT_RUNNING_SENTINEL = "machine_not_running"
BOOT_RETRIES = 8
BOOT_WAIT_S = 6.0

# Where the CLI installs by default when it is not on PATH.
_FALLBACK_BOX_EXE = os.path.expanduser("~/.ascii/bin/box")


class BoxError(RuntimeError):
    """A `box` CLI call failed, carrying the CLI's own last message."""


def resolve_box_exe() -> Optional[str]:
    """The `box` executable, from PATH or the default install location.

    PATH first so a dev override wins; the fallback exists because the shell
    integration defines `box` as a *function*, which a subprocess never sees.
    """
    found = shutil.which("box")
    if found:
        return found
    return _FALLBACK_BOX_EXE if os.path.isfile(_FALLBACK_BOX_EXE) else None


def still_booting(output: str) -> bool:
    """True if a `box ssh` result means the machine is not up yet (retry it)."""
    return MACHINE_NOT_RUNNING_SENTINEL in (output or "")


@dataclass
class BoxRecord:
    """The subset of a box payload this lab uses."""

    id: str
    state: str = ""
    raw: dict = None

    @property
    def is_ready(self) -> bool:
        return self.state.lower() in READY_STATES


def parse_box(payload: dict) -> Optional[BoxRecord]:
    """Coerce a bare or wrapped box payload into a record (schema-tolerant).

    Key spellings vary across `new` / `info` / `list`; tolerate the shapes rather
    than pin one, so a server-side rename degrades to a missing field instead of
    a crash mid-run.
    """
    if not isinstance(payload, dict):
        return None
    node = payload
    for key in ("box", "data"):
        inner = payload.get(key)
        if isinstance(inner, dict):
            node = inner
            break
    else:
        boxes = payload.get("boxes")
        if isinstance(boxes, list) and boxes and isinstance(boxes[0], dict):
            node = boxes[0]
    box_id = node.get("id") or node.get("box_id") or node.get("boxId")
    if not box_id:
        return None
    state = node.get("state") or node.get("status") or ""
    return BoxRecord(id=str(box_id), state=str(state), raw=node)


class BoxController:
    """Guarded writes against the Box platform via the `box` CLI."""

    def __init__(self, exe: Optional[str] = None) -> None:
        self._exe_path = exe or resolve_box_exe()

    def _exe(self) -> str:
        if not self._exe_path:
            raise BoxError(
                "box CLI not found on PATH or at ~/.ascii/bin/box — "
                "install it with: curl -fsSL https://box.ascii.dev/install | sh")
        return self._exe_path

    # ---- low-level --------------------------------------------------------

    def _box_json(self, *args: str, timeout: float = 60.0) -> dict:
        proc = subprocess.run(
            [self._exe(), "--json", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise BoxError(msg[-1] if msg else f"box {' '.join(args)} failed")
        return self._parse_json_or_jsonl(proc.stdout)

    @staticmethod
    def _parse_json_or_jsonl(text: str) -> dict:
        """Parse one JSON object, or the last box-bearing object from JSONL."""
        text = (text or "").strip()
        if not text:
            raise BoxError("box returned empty output")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
        objs = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                objs.append(obj)
        if not objs:
            raise BoxError("box returned no parseable JSON object")
        # An `{"event":"error",...}` line is the CLI's real verdict — surface it
        # rather than returning an earlier, misleadingly healthy progress line.
        for obj in reversed(objs):
            if obj.get("event") == "error":
                raise BoxError(obj.get("error") or obj.get("code") or "box error")
        for obj in reversed(objs):
            if {"id", "box", "boxes"} & obj.keys():
                return obj
        return objs[-1]

    # ---- lifecycle --------------------------------------------------------

    def create(self, *, ttl: int = 21600) -> BoxRecord:
        """Create a CPU box and poll until it reports a ready state.

        A TTL is mandatory in practice, not optional: it is the only backstop
        against a run that dies without freeing its box. `box new` also rejects
        `--ttl` together with `--no-auto-stop`, so this lab always takes the TTL.
        """
        args = ["new"]
        if ttl:
            args += ["--ttl", str(int(ttl))]
        created = parse_box(self._box_json(*args, timeout=180.0))
        if created is None:
            raise BoxError("box new returned no box id")

        deadline = time.monotonic() + CREATE_TIMEOUT_S
        latest = created
        while time.monotonic() < deadline:
            if latest.is_ready:
                return latest
            time.sleep(CREATE_POLL_S)
            info = parse_box(self._box_json("info", created.id, timeout=30.0))
            if info is not None:
                latest = info
        return latest  # bounded wait elapsed — hand back what we last saw

    def info(self, box_id: str) -> Optional[BoxRecord]:
        return parse_box(self._box_json("info", box_id, timeout=30.0))

    def stop(self, box_id: str) -> dict:
        return self._box_json("stop", box_id, timeout=120.0)

    def resume(self, box_id: str) -> dict:
        return self._box_json("resume", box_id, timeout=180.0)

    def delete(self, box_id: str) -> dict:
        return self._box_json("delete", box_id, timeout=120.0)

    def fork(self, box_id: str) -> Optional[BoxRecord]:
        """Fork a box from its latest snapshot (the identical-arms primitive)."""
        return parse_box(self._box_json("fork", box_id, timeout=180.0))

    # ---- ssh --------------------------------------------------------------

    def ssh_exec(self, box_id: str, script: str, *, stream: bool = False,
                 timeout: Optional[float] = 600.0,
                 on_line: Optional[Callable[[str], None]] = None
                 ) -> Tuple[int, str]:
        """Run a bash `script` on the box, piped on **stdin** (never argv).

        Returns `(returncode, combined_output)`. Callers that launch detached
        work must treat `subprocess.TimeoutExpired` as success — see
        `runner.launch`.
        """
        return self._run([self._exe(), "ssh", box_id, "bash", "-s"],
                         input_text=script, stream=stream, timeout=timeout,
                         on_line=on_line)

    def ssh_args(self, box_id: str, args: List[str], *, stream: bool = False,
                 timeout: Optional[float] = 60.0,
                 on_line: Optional[Callable[[str], None]] = None
                 ) -> Tuple[int, str]:
        """Run a direct command on the box (`timeout=None` for `tail -f`)."""
        return self._run([self._exe(), "ssh", box_id, *args],
                         input_text=None, stream=stream, timeout=timeout,
                         on_line=on_line)

    def await_ssh_ready(self, box_id: str) -> bool:
        """Probe until the machine answers ssh. True if it did, within bounds.

        Returning False is not fatal on its own — the caller's real script will
        surface the error — but it is worth logging, because every later symptom
        of this condition looks like something else.
        """
        for _ in range(BOOT_RETRIES):
            try:
                _, out = self.ssh_exec(box_id, "echo BOXLAB_SSH_OK\n", timeout=30.0)
            except subprocess.TimeoutExpired:
                return True  # connected, probe just didn't return — machine is up
            except BoxError:
                out = MACHINE_NOT_RUNNING_SENTINEL
            if not still_booting(out):
                return True
            time.sleep(BOOT_WAIT_S)
        return False

    @staticmethod
    def _run(argv: List[str], *, input_text: Optional[str], stream: bool,
             timeout: Optional[float],
             on_line: Optional[Callable[[str], None]] = None) -> Tuple[int, str]:
        if not stream:
            proc = subprocess.run(argv, input=input_text, capture_output=True,
                                  text=True, timeout=timeout)
            return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if input_text is not None and proc.stdin is not None:
            proc.stdin.write(input_text)
            proc.stdin.close()
        chunks: List[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if on_line is not None:
                    on_line(line.rstrip("\n"))
                else:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                chunks.append(line)
            proc.wait(timeout=timeout)
        except KeyboardInterrupt:
            proc.terminate()
            return 130, "".join(chunks)
        return proc.returncode or 0, "".join(chunks)
