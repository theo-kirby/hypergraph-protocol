"""Strip live credentials out of anything harvested off a box.

The nine-run benchmark leaked. Agents ran `cat ~/research/.env` — thirty times
across six of nine runs — and the harness dutifully archived the transcripts,
live `OPENROUTER_API_KEY`, `GITHUB_TOKEN` and `FLYWHEEL_API_KEY` included, into
git-tracked files. The harvest already excluded `.env` *at the source*, which was
the right instinct at the wrong scope: excluding the file does nothing about the
agent that printed its contents into a transcript.

So redaction happens **in memory, before the first write**. `_harvest` decodes
the archive, rewrites its text members through `redact_archive`, and only then
touches disk. An archive that briefly holds a live token on a laptop is a leak
that already happened; there is no cleanup afterwards that undoes it.

Two layers, because either alone is insufficient:

1. **Known values** (`secret_values`) — exact substring replacement of every
   secret this process holds. Precise, and blind to anything it was not told.
2. **Shapes** (`SECRET_SHAPES`) — regexes for credentials whose *form* is
   recognisable: `sk-or-v1-…`, `ghp_…`, `github_pat_…`, and a long opaque value
   sitting after an `…_API_KEY=`. This is what catches a key the operator
   rotated last week, a token an agent minted itself, or a second account
   nobody registered with the lab.

`MIN_SECRET_LEN` is the one number worth arguing about. A short value —
`GITHUB_OWNER`, a two-character flag — appears inside ordinary prose, and
replacing it would corrupt every transcript while protecting nothing. Values
below the floor are dropped here; `preflight` is the layer that refuses to launch
over a credential too short to be one.
"""

from __future__ import annotations

import io
import re
import tarfile
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

# A finding is (path, line number, credential label).
Finding = Tuple[str, int, str]

# Variables whose *value* is a credential. `GITHUB_OWNER` is deliberately absent:
# it is an account name, it is public, and it is short enough that redacting it
# would mangle every URL in every transcript.
SECRET_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    "FLYWHEEL_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "BOX_API_KEY",
    "KAGGLE_API_TOKEN",
)

# Below this, a "secret" is more likely a placeholder or a flag than a key, and
# blanket-replacing it would corrupt the transcript it was meant to protect.
MIN_SECRET_LEN = 12

# Credentials recognisable by shape alone — the safety net under `secret_values`.
# Each entry is (label, compiled pattern). When the pattern has a group, only the
# group is replaced, so the `KEY=` prefix survives: a reader can still see *that*
# a key was printed, and which variable it was, without the value.
SECRET_SHAPES: Tuple[Tuple[str, re.Pattern], ...] = (
    ("CLAUDE_CODE_OAUTH_TOKEN", re.compile(r"sk-ant-oat[A-Za-z0-9_\-]{16,}")),
    ("ANTHROPIC_API_KEY", re.compile(r"sk-ant-(?!oat)[A-Za-z0-9_\-]{16,}")),
    ("OPENROUTER_API_KEY", re.compile(r"sk-or-v1-[A-Za-z0-9]{16,}")),
    ("OPENAI_API_KEY", re.compile(r"sk-proj-[A-Za-z0-9_\-]{16,}")),
    ("GITHUB_TOKEN", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}")),
    # A long opaque value assigned to something that calls itself a key, token
    # or secret. Anchored on the assignment, so ordinary prose containing a long
    # word is untouched.
    ("API_KEY", re.compile(
        r"(?i)[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)\s*[=:]\s*"
        r"[\"']?([A-Za-z0-9_\-\.+/]{24,})")),
    # A bearer header is a credential wherever it appears.
    ("BEARER", re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-\.+/]{20,})")),
)

# What the scanner looks for when asserting a tree is clean. Deliberately the
# same shapes: a test that scanned for different patterns than redaction removes
# would pass on data redaction never touched.
SCAN_SHAPES = SECRET_SHAPES

REDACTED_PREFIX = "<REDACTED:"


def placeholder(name: str) -> str:
    return f"{REDACTED_PREFIX}{name}>"


def secret_values(values: Mapping[str, Optional[str]]) -> Dict[str, str]:
    """Map every *credential* in a resolved config to its variable name.

    Accepts `LabConfig.values` (or any mapping). Non-secret names, empty values
    and implausibly short values are dropped. Per-run Flywheel keys
    (`FLYWHEEL_API_KEY_HYPERGRAPH_S2` and friends) are picked up by prefix, so
    adding a seed's key to `.env` does not also require editing a list here to
    keep it out of the archives.
    """
    out: Dict[str, str] = {}
    for name, value in values.items():
        if not value or not isinstance(value, str):
            continue
        is_secret = (name in SECRET_ENV_VARS
                     or name.startswith("FLYWHEEL_API_KEY")
                     or name.endswith(("_API_KEY", "_TOKEN", "_SECRET")))
        if not is_secret or len(value) < MIN_SECRET_LEN:
            continue
        out[name] = value
    return out


def _shape_sub(match: re.Match, name: str) -> str:
    """Replace the credential inside a shape match, keeping any `KEY=` prefix."""
    token = placeholder(name)
    if not match.re.groups:
        return token
    group = match.group(1)
    if group is None:
        return token
    whole = match.group(0)
    cut = whole.rindex(group)
    return whole[:cut] + token + whole[cut + len(group):]


def redact(text: str, secrets: Mapping[str, str]) -> str:
    """Replace every known secret value, then every secret-*shaped* run.

    Known values go first and **longest first**: when one credential is a prefix
    of another (an account key and a scoped key derived from it, say), replacing
    the short one first would leave the long one's tail in the output as an
    orphaned fragment.
    """
    if not text:
        return text
    by_length = sorted(((v, n) for n, v in secrets.items()
                        if v and len(v) >= MIN_SECRET_LEN),
                       key=lambda pair: len(pair[0]), reverse=True)
    for value, name in by_length:
        if value in text:
            text = text.replace(value, placeholder(name))

    for name, pattern in SECRET_SHAPES:
        text = pattern.sub(lambda m, n=name: _shape_sub(m, n), text)
    return text


def redact_bytes(blob: bytes, secrets: Mapping[str, str]) -> bytes:
    """Redact a member's bytes if it decodes as text; pass binary through.

    Binary members (a `.so`, a gzip, a numpy dump) are returned untouched. A
    credential *can* sit inside a binary, but replacing bytes in one changes its
    length and corrupts it, and these archives' binaries are build outputs rather
    than transcripts. Text is where the leak was, and text is what is rewritten.
    """
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob
    cleaned = redact(text, secrets)
    return cleaned.encode("utf-8") if cleaned != text else blob


# Members worth decoding at all. Everything else is copied through byte-for-byte,
# which keeps a 60 MB vectors.txt from being decoded, scanned and re-encoded for
# nothing — it is 71k lines of floats and cannot carry a credential shape.
TEXTUAL_SUFFIXES = (
    ".jsonl", ".json", ".md", ".txt", ".log", ".py", ".sh", ".c", ".h",
    ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env", ".csv", ".html", ".js",
)

# …with one exception: the vector dumps really are just numbers, and they are the
# largest thing in an archive by an order of magnitude.
_SKIP_BASENAME_PREFIXES = ("vectors", "text8")

# A member bigger than this is not read into memory to be redacted. Stated as a
# constant rather than buried, because the trade-off is real: a credential in a
# 200 MB file would survive. Nothing that large in these archives is a
# transcript, and holding one in memory alongside the archive is how a harvest
# gets OOM-killed on a laptop.
MAX_REDACT_BYTES = 64 * 1024 * 1024


def _is_textual(name: str, size: int) -> bool:
    base = name.rsplit("/", 1)[-1]
    if size > MAX_REDACT_BYTES:
        return False
    if any(base.startswith(prefix) for prefix in _SKIP_BASENAME_PREFIXES):
        return False
    return base.endswith(TEXTUAL_SUFFIXES)


def redact_archive(blob: bytes, secrets: Mapping[str, str]) -> Tuple[bytes, int]:
    """Rewrite a `.tar.gz` in memory, redacting its text members.

    Returns `(archive_bytes, members_changed)`. On any tar-level failure the
    original bytes come back with a count of `-1`: a harvest that cannot be
    rewritten must still reach the caller, which decides whether an unredactable
    archive is worth keeping. Returning empty would lose the run's only copy of
    its evidence to protect it from a leak that may not be there.
    """
    secrets = secrets or {}
    try:
        src = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError):
        return blob, -1

    out = io.BytesIO()
    changed = 0
    try:
        with src, tarfile.open(fileobj=out, mode="w:gz") as dst:
            for member in src:
                if not member.isfile():
                    dst.addfile(member)
                    continue
                handle = src.extractfile(member)
                if handle is None:
                    dst.addfile(member)
                    continue
                data = handle.read()
                if _is_textual(member.name, member.size):
                    cleaned = redact_bytes(data, secrets)
                    if cleaned != data:
                        changed += 1
                        data = cleaned
                        member = _resized(member, len(data))
                dst.addfile(member, io.BytesIO(data))
    except (tarfile.TarError, OSError, EOFError):
        return blob, -1
    return out.getvalue(), changed


def _resized(member: tarfile.TarInfo, size: int) -> tarfile.TarInfo:
    """A copy of `member` with a corrected size — redaction changes lengths."""
    clone = tarfile.TarInfo(name=member.name)
    clone.size = size
    clone.mtime = member.mtime
    clone.mode = member.mode
    clone.type = member.type
    clone.uid, clone.gid = member.uid, member.gid
    clone.uname, clone.gname = member.uname, member.gname
    return clone


# ---- scanning: the test's half of the contract --------------------------------

def scan_text(text: str, *, label_path: str = "") -> List[Finding]:
    """Every secret-shaped run in `text`, as `(path, line_no, label)`.

    A line that is *already* redacted is not a finding — otherwise the `API_KEY=`
    shape would flag its own placeholder forever and the scan could never pass.
    """
    findings: List[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in SCAN_SHAPES:
            for match in pattern.finditer(line):
                hit = (match.group(1) if match.re.groups and match.group(1)
                       else match.group(0))
                if hit.startswith(REDACTED_PREFIX):
                    continue
                findings.append((label_path, lineno, name))
                break
    return findings


def scan_paths(paths: Iterable[Path]) -> List[Finding]:
    """Scan files on disk. Unreadable, oversized and binary files are skipped."""
    findings: List[Finding] = []
    for path in paths:
        try:
            if not path.is_file() or path.stat().st_size > MAX_REDACT_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(text, label_path=str(path)))
    return findings


def scan_tree(root: Path, *, suffixes: Iterable[str] = TEXTUAL_SUFFIXES
              ) -> List[Finding]:
    """Scan every textual file under `root`."""
    wanted = tuple(suffixes)
    if not root.exists():
        return []
    return scan_paths(p for p in root.rglob("*")
                      if p.is_file() and p.name.endswith(wanted))
