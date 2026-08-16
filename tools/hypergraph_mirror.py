"""The optional one-way mirror (backend/mirror.md) — the networked half.

Loaded lazily and exclusively through `hypergraph_core._mirror()`, which registers
the running core module under the name `hypergraph_core` before executing this
file, so the `import hypergraph_core as core` below binds to the same module
object whichever name core runs under (`__main__`, `hypergraph_protocol`, or a
test fixture). Offline commands never import this file at all — that is the
split's contract, and tests/test_mirror_split.py holds it.

Patchable/tunable core symbols are accessed as `core.<attr>` (never from-imported)
so a monkeypatch on the core module is seen here too.

Deliberately not a script: no PEP 723 header, no entry point. Everything here
needs core loaded first.
"""
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("hypergraph_mirror is not a command — run hypergraph.py, "
                     "which loads it on demand.")

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import hypergraph_core as core


class MirrorError(core.LocalGraphError):
    """Anything wrong on the mirror path.

    Subclasses LocalGraphError, so main()'s existing handler renders every one of
    these as `error: <one line>` and exits 2 with no extra plumbing."""


class MirrorUnavailable(MirrorError):
    """No usable transport: the binary is absent, or no credentials exist."""


class MirrorAuthError(MirrorError):
    """401/403. Aborts before any node file is stamped — a key that can read but not
    write must not leave the graph half-pushed."""


class MirrorConflict(MirrorError):
    """409. Never blind-retried: under SPEC I3 there is one writer, so a conflict is
    evidence that something else wrote."""


class MirrorRateLimited(MirrorError):
    """429. Carries the server's Retry-After when it supplied one."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class MirrorNode:
    """One node as the host returned it. Constructed only through `from_raw`."""
    node_id: str
    slug: str
    title: str
    content: str
    summary: str
    revision: int | None
    can_write: bool | None = None
    is_owner: bool | None = None

    @property
    def sha256(self) -> str:
        return core.body_sha256(self.content)

    @staticmethod
    def _bool(value: object) -> bool | None:
        # the CLI stringifies booleans in JSON output ("True"/"False")
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        return None

    @classmethod
    def from_raw(cls, raw: object, *, context: str, need_revision: bool = True) -> "MirrorNode":
        """Probe the response shape and fail loudly.

        Every mutating endpoint's success schema in the live OpenAPI is literally
        `{}`, so nothing here may be assumed. In particular **never default
        `revision` to 0**: `revision: 0` is a real value (this repo's own mirror
        roots sit at 0), and a wrongly-defaulted 0 makes every later update conflict
        forever. An absent revision stays `None`, and the caller must read the live
        one rather than invent it."""
        if isinstance(raw, dict) and isinstance(raw.get("node"), dict):
            raw = raw["node"]  # some responses wrap the node
        if not isinstance(raw, dict):
            raise MirrorError(f"{context}: expected a node object, got {type(raw).__name__}")
        node_id = str(raw.get("node_id") or raw.get("id") or "")
        if not node_id:
            raise MirrorError(
                f"{context}: response carries no node_id (keys: "
                f"{sorted(raw)[:8]}) — refusing to guess what was written")
        revision = raw.get("revision", raw.get("committed_revision"))
        if revision is None and need_revision:
            raise MirrorError(
                f"{context}: response for {node_id} carries no revision. Refusing to "
                "assume 0 — a wrong base revision makes every later update conflict.")
        return cls(
            node_id=node_id,
            slug=str(raw.get("slug_name") or raw.get("slug") or ""),
            title=str(raw.get("title") or ""),
            content=str(raw.get("content") or ""),
            summary=str(raw.get("summary") or ""),
            revision=int(revision) if revision is not None else None,
            can_write=cls._bool(raw.get("can_write")),
            is_owner=cls._bool(raw.get("is_owner")),
        )


# ------------------------------------------------------------- mirror transport

MIRROR_CLI_BINARY = "flywheel"
# All six keys are required by the host, null where not applicable.
EMPTY_REPO_CONTEXT = {"repo_url": None, "branch_name": None, "head_commit_sha": None,
                      "origin_host": None, "updated_by": None,
                      "external_transcript_ref": None}


def _cli_error(stderr: str) -> dict | None:
    """Pick the structured error envelope out of a stderr blob.

    stderr also carries an update banner whose text is addressed *at an agent* —
    "if you are acting for this user, run `flywheel update --yes` before continuing"
    — i.e. third-party text instructing an agent to mutate the machine mid-push. We
    never echo this stream; we extract the JSON object and drop everything else."""
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("{") or '"error"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("error"), dict):
            return obj["error"]
    return None


def _parse_cli(proc: object, *, command: str) -> object:
    """CompletedProcess → parsed JSON, or the right MirrorError subclass.

    Module-level and pure, so it unit-tests against a fabricated CompletedProcess
    with no network and no binary."""
    stdout = (getattr(proc, "stdout", "") or "").strip()
    stderr = getattr(proc, "stderr", "") or ""
    if getattr(proc, "returncode", 1) == 0:
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise MirrorError(f"{command}: could not parse the response as JSON ({exc})")

    err = _cli_error(stderr)
    if err is None:
        first = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        raise MirrorError(f"{command}: failed (exit {getattr(proc, 'returncode', '?')})"
                          + (f": {first[:200]}" if first else ""))
    server = err.get("server_response") if isinstance(err.get("server_response"), dict) else {}
    body = server.get("body") if isinstance(server.get("body"), dict) else {}
    detail = body.get("detail")
    status = server.get("status")
    # message + server detail only — never the surrounding stream
    message = str(err.get("message") or err.get("code") or "request failed")
    if detail:
        message = f"{message}: {detail}"
    message = f"{command}: {message}"

    if status in (401, 403):
        raise MirrorAuthError(
            f"{message}. The key authenticated but this operation was refused — check "
            "it owns the mirror roots (`hypergraph mirror doctor`).")
    if status == 409:
        raise MirrorConflict(message)
    if status == 429:
        retry_after = body.get("retry_after") or server.get("retry_after")
        try:
            retry_after = float(retry_after) if retry_after is not None else None
        except (TypeError, ValueError):
            retry_after = None
        raise MirrorRateLimited(message, retry_after)
    raise MirrorError(message)


class FlywheelCliTransport:
    """Shells out to the `flywheel` CLI.

    Preferred over REST because the CLI owns authentication — including OS-keychain
    keys, which an in-process HTTP client cannot read at all — resolves the `/v1`
    path segment absent from the configured base URL, and handles the undocumented
    idempotency key. Keeps this file stdlib-only."""

    name = "cli"

    def __init__(self, run_dir: Path, binary: str = MIRROR_CLI_BINARY,
                 env_profile: str | None = None):
        self.binary = binary
        self.env_profile = env_profile
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._payload_seq = 0

    @staticmethod
    def available(binary: str = MIRROR_CLI_BINARY) -> bool:
        return shutil.which(binary) is not None

    def version(self) -> str:
        """Logged for the record, never acted on."""
        try:
            proc = subprocess.run([self.binary, "--version"], capture_output=True,
                                  text=True, timeout=30)
            return (proc.stdout or proc.stderr or "").strip().splitlines()[0][:60]
        except (OSError, subprocess.SubprocessError, IndexError):
            return "unknown"

    def _run(self, command: str, *, payload: dict | None = None,
             files: dict | None = None, extra: list[str] | None = None, **flags) -> object:
        argv = [self.binary, command, "--format=json"]
        if self.env_profile:
            argv += [f"--env={self.env_profile}"]
        for key, value in flags.items():
            if value is None:
                continue
            argv += [f"--{key}={value}"]
        # Always a file, never inline: node bodies are multi-KB, an artifact `items`
        # list is multi-KB again, argv limits are platform-dependent, and a leftover
        # `items-00007.json` is free forensics on a crash. `payload` is sugar over
        # `files` so there stays exactly **one** place that writes a run-dir file and
        # renders an `@` flag.
        writes = [("payload_json", "payload", payload)] if payload is not None else []
        writes += [(key, key, value) for key, value in (files or {}).items()]
        for flag, stem, value in writes:
            self._payload_seq += 1
            path = self.run_dir / f"{stem}-{self._payload_seq:05d}.json"
            path.write_text(json.dumps(value, ensure_ascii=False))
            argv += [f"--{flag}=@{path}"]
        argv += extra or []
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            raise MirrorUnavailable(
                f"`{self.binary}` is not on PATH. Install it (npm i -g "
                "@paradigma-inc/flywheel) or run with --transport rest, which needs "
                "FLYWHEEL_BASE_URL and FLYWHEEL_API_KEY in the environment.")
        except subprocess.TimeoutExpired:
            raise MirrorError(f"{command}: timed out after 600s")
        return _parse_cli(proc, command=command)

    # --- the seven operations ------------------------------------------------
    def auth_status(self) -> dict:
        raw = self._run("auth:status")
        return raw if isinstance(raw, dict) else {}

    def get_node(self, node_id: str) -> MirrorNode:
        raw = self._run("nodes:get", node_id=node_id, projection="core")
        return MirrorNode.from_raw(raw, context=f"nodes:get {node_id}")

    def children(self, node_id: str):
        """Yield every direct child, paging to exhaustion.

        The cursor loop is not optional: a record root with more than one page of
        children silently misses an existing legend node without it, and then
        creates a second one on every push (backend/mirror.md)."""
        after = None
        seen = 0
        while True:
            raw = self._run("nodes:children", node_id=node_id, first=500,
                            projection="core", after=after)
            if not isinstance(raw, dict):
                raise MirrorError(f"nodes:children {node_id}: unexpected response shape")
            edges = raw.get("edges") or []
            for edge in edges:
                node = edge.get("node") if isinstance(edge, dict) else None
                if isinstance(node, dict):
                    seen += 1
                    yield MirrorNode.from_raw(node, context=f"nodes:children {node_id}",
                                              need_revision=False)
            page = raw.get("page_info") if isinstance(raw.get("page_info"), dict) else {}
            if MirrorNode._bool(page.get("has_next_page")) is not True:
                return
            after = page.get("end_cursor")
            if not after:
                return

    def commit_new(self, *, parent_ids: list[str], title: str, content: str,
                   summary: str = "", repo_context: dict | None = None,
                   temp_id: str | None = None) -> MirrorNode:
        payload = {
            "local_temp_node_id": temp_id or f"hypergraph-{core.uuid.uuid4()}",
            "parent_ids": [p for p in parent_ids if p],
            "staged_payload": {
                "title": title, "content": content, "summary": summary,
                "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT),
            },
        }
        raw = self._run("nodes:commit-new", payload=payload)
        return MirrorNode.from_raw(raw, context="nodes:commit-new", need_revision=False)

    def commit(self, *, node_id: str, base_revision: int, title: str, content: str,
               summary: str = "", repo_context: dict | None = None) -> MirrorNode:
        """acquire → commit → release, with the release in a `finally`.

        The whole lease dance lives here so 409 semantics exist in exactly one
        place."""
        session = f"hypergraph-{core.uuid.uuid4()}"
        self._run("nodes:stage:lease:acquire", node_id=node_id,
                  stage_session_id=session, base_committed_revision=base_revision)
        try:
            raw = self._run("nodes:commit", node_id=node_id, payload={
                "stage_session_id": session,
                "base_committed_revision": base_revision,
                "staged_payload": {
                    "title": title, "content": content, "summary": summary,
                    "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT),
                },
            })
        finally:
            try:
                self._run("nodes:stage:lease:release", node_id=node_id,
                          stage_session_id=session)
            except MirrorError:
                pass  # the commit's outcome is what matters; leases expire on their own
        return MirrorNode.from_raw(raw, context=f"nodes:commit {node_id}",
                                   need_revision=False)

    def export_subgraph(self, node_ids: list[str], out: Path, *,
                        include_descendants: bool = True, max_nodes: int = 5000) -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._run("export:subgraph", node_ids=",".join(node_ids),
                  include_descendants="true" if include_descendants else "false",
                  max_nodes=max_nodes, extra=[f"--out={out}"])
        if not out.exists():
            raise MirrorError(f"export:subgraph wrote no file at {out}")
        return out

    def delete_node(self, node_id: str, *, mode: str = "detach_shared") -> None:
        self._run("nodes:delete", node_id=node_id, delete_mode=mode, extra=["--yes"])

    # --- re-parenting ----------------------------------------------------------
    # Not an INTERFACE operation — a topology repair (backend/flywheel.md). Both are
    # graph writes and both take **four** optimistic locks, two per endpoint. Nothing
    # here re-reads them: the caller does, immediately before each call, because the
    # add bumps the child and a revision computed once and reused across a batch is
    # stale after the first edge.
    def add_parent(self, *, node_id: str, parent_id: str, expected_revision: int,
                   expected_parent_revision: int) -> None:
        self._run("nodes:add-parent", node_id=node_id, parent_id=parent_id,
                  expected_revision=int(expected_revision),
                  expected_parent_revision=int(expected_parent_revision))

    def remove_parent(self, *, node_id: str, parent_id: str, expected_revision: int,
                      expected_parent_revision: int) -> None:
        self._run("nodes:remove-parent", node_id=node_id, parent_id=parent_id,
                  expected_revision=int(expected_revision),
                  expected_parent_revision=int(expected_parent_revision))

    # --- op 10: tags -----------------------------------------------------------
    def graph_tags(self, root_node_id: str) -> tuple[list[dict], int]:
        """The vocabulary on one graph root, plus that root's current revision.

        There is **no `tags:list`**. The vocabulary comes back on any node under
        `--projection full`, as `graph_tags`. An absent key **raises**: reading it as
        "this graph has no tags" would make the next push re-create all 22 of them,
        which is the duplicate-definition failure this whole feature guards against."""
        raw = self._run("nodes:get", node_id=root_node_id, projection="full")
        return _parse_graph_tags(raw, context=f"nodes:get {root_node_id} (full)")

    def create_tag(self, *, root_node_id: str, name: str, expected_revision: int,
                   bg_color: str, text_color: str, one_only: bool = False,
                   track_history: bool = False) -> dict:
        """One `tags:create`. **Never blind-retried** — creates cannot be de-duplicated.

        `expected_revision` must be re-read before every call: each create bumps the
        root revision, so a revision computed once and reused across a 22-tag loop is
        stale after the first.

        **The return value is not the tag's identity.** Measured against the live host:
        this endpoint returns the updated *graph root node* — `content`, `artifacts`,
        `graph_projection` — with no `tag_id` anywhere in it. The caller re-reads the
        root and resolves the new tag **by name**, which is the same rule as never
        assuming a revision, and is also exactly the recovery path a crashed run
        needs."""
        # argv trap: `_run` renders `--{k}={v}` for anything non-None, so a Python
        # False would become the *truthy string* `--one_only=False`. These are
        # store-true flags — omit them, or pass them bare.
        extra = (["--one_only"] if one_only else []) + \
                (["--track_history"] if track_history else [])
        raw = self._run("tags:create", root_node_id=root_node_id, name=name,
                        expected_revision=int(expected_revision), bg_color=bg_color,
                        text_color=text_color, extra=extra)
        return raw if isinstance(raw, dict) else {}

    def assign_tags(self, *, node_id: str, tag_ids: list[str],
                    expected_revision: int) -> None:
        """Atomic replace of a node's whole tag set. Bumps the *node* revision."""
        self._run("tags:assign", node_id=node_id, tag_ids=",".join(tag_ids),
                  expected_revision=int(expected_revision))

    # --- op 9: artifacts -------------------------------------------------------
    def artifacts(self, node_id: str) -> tuple[list[dict], int]:
        """Everything attached to one node, plus that node's current revision.

        **One read answers both of `push_artifacts`'s questions**: the dedupe set (by
        title) and the `expected_revision` the upload locks against. That single fact
        carries the whole idempotency design — the listing is needed anyway, so
        dropping already-attached items costs nothing extra.

        Measured against the installed CLI (0.1.108): `artifacts:list` accepts
        `--limit` and **has no `--offset`**, and the server silently clamps `limit` to
        200. So this transport cannot page, and a node past that ceiling raises rather
        than returning a first page — a truncated listing reads as "these are not
        attached" and uploads them all again, which is the one failure nothing here
        can undo."""
        raw = self._run("artifacts:list", node_id=node_id, limit=core.ARTIFACT_LIST_LIMIT)
        records, revision, has_more, _next = _parse_artifact_list(
            raw, context=f"artifacts:list {node_id}", offset=0)
        if has_more:
            raise MirrorError(
                f"artifacts:list {node_id}: more than {core.ARTIFACT_LIST_LIMIT} artifacts "
                "are attached, and this CLI's `artifacts:list` has no `--offset` to "
                "page with. Refusing to treat the first page as the whole listing — "
                "that would re-upload everything past it. Use `--transport rest`, "
                "which pages by offset.")
        return records, revision

    def upload_artifacts(self, *, node_id: str, expected_revision: int,
                         items: list[dict]) -> object:
        """One batch: prepare + PUT + finalize, inside the CLI, in one process.

        **Finalize appends the whole batch with a single revision bump**, so one batch
        is one bump and one unit of recovery. Never blind-retried — see
        `push_artifacts`."""
        return self._run("artifacts:upload", node_id=node_id,
                         expected_revision=int(expected_revision),
                         files={"items": list(items)})


def _parse_artifact_list(raw: object, *, context: str, offset: int
                         ) -> tuple[list[dict], int, bool, int]:
    """One `artifacts:list` page → (artifacts, node_revision, has_more, next offset).

    Three absences that must raise rather than default, all for the same reason:
    every one of them, read charitably, produces a **duplicate upload**, and this
    design never calls `artifacts:delete`, so a duplicate is permanent.

    - no `artifacts` key → "nothing is attached" → re-upload every item. The
      `_parse_graph_tags` rule, one noun over.
    - no `node_revision` → assume 0 → the same refusal as `MirrorNode.from_raw`.
    - an `offset` that does not advance → an unpaged read that silently sees only the
      first page and re-uploads the rest. This is the legend-paging incident with a
      different noun, and it is the one that would go unnoticed longest.
    """
    if not isinstance(raw, dict):
        raise MirrorError(f"{context}: expected an object, got {type(raw).__name__}")
    if "artifacts" not in raw:
        raise MirrorError(
            f"{context}: the response carries no `artifacts` key (keys: "
            f"{sorted(raw)[:10]}). Refusing to read that as \"this node has no "
            "artifacts\" — that would upload every one of them a second time, and "
            "nothing here ever calls `artifacts:delete` to undo it.")
    records = [a for a in (raw.get("artifacts") or []) if isinstance(a, dict)]
    revision = raw.get("node_revision", raw.get("revision"))
    if revision is None:
        raise MirrorError(
            f"{context}: no `node_revision` on the listing. The upload locks against "
            "it, and refusing to assume 0 is the same rule as everywhere else here.")
    has_more = MirrorNode._bool(raw.get("has_more")) is True
    try:
        page_offset = int(raw.get("offset"))
    except (TypeError, ValueError):
        page_offset = offset
    next_offset = page_offset + len(records)
    if has_more and next_offset <= offset:
        raise MirrorError(
            f"{context}: `has_more` is set but the page did not advance past offset "
            f"{offset} ({len(records)} record(s) at offset {page_offset}). An unpaged "
            "read is a duplicate generator — refusing to loop.")
    return records, int(revision), has_more, next_offset


def artifact_id_of(raw: dict) -> str:
    return str(raw.get("artifact_id") or raw.get("id") or "")


def _parse_graph_tags(raw: object, *, context: str) -> tuple[list[dict], int]:
    """A full-projection node response → (its graph's tag definitions, root revision)."""
    if isinstance(raw, dict) and isinstance(raw.get("node"), dict):
        raw = raw["node"]
    if not isinstance(raw, dict):
        raise MirrorError(f"{context}: expected a node object, got {type(raw).__name__}")
    if "graph_tags" not in raw:
        raise MirrorError(
            f"{context}: the response carries no `graph_tags` key (keys: "
            f"{sorted(raw)[:10]}). Refusing to read that as \"this graph has no "
            "tags\" — that would re-create the whole vocabulary on the next push, "
            "and a duplicate tag definition cannot be cleanly merged.")
    tags = [t for t in (raw.get("graph_tags") or []) if isinstance(t, dict)]
    revision = raw.get("revision", raw.get("committed_revision"))
    if revision is None:
        raise MirrorError(
            f"{context}: no revision on the root. `tags:create` locks against it and "
            "refusing to assume 0 is the same rule as everywhere else here.")
    return tags, int(revision)


def tag_by_name(tags: list[dict], name: str) -> dict | None:
    """A tag definition out of a root's `graph_tags`, by name.

    Name is the only lookup key here, deliberately. It is what makes a create
    idempotent by inspection — a crashed run finds the tag rather than repeating it —
    and it is what identifies a tag whose id the create response never returned."""
    for tag in tags:
        if isinstance(tag, dict) and str(tag.get("name") or "") == name:
            return tag
    return None


class FlywheelRestTransport(FlywheelCliTransport):
    """Explicit fallback for machines without the npm binary.

    Same seven operations over `urllib`. It cannot read OS-keychain keys, so it
    requires FLYWHEEL_BASE_URL and FLYWHEEL_API_KEY in the environment."""

    name = "rest"

    def __init__(self, run_dir: Path, base_url: str, api_key: str):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._payload_seq = 0

    @staticmethod
    def from_env(run_dir: Path) -> "FlywheelRestTransport":
        import os  # deferred: nothing off the mirror path reads the environment
        base = os.environ.get("FLYWHEEL_BASE_URL", "").strip()
        key = os.environ.get("FLYWHEEL_API_KEY", "").strip()
        if not base or not key:
            raise MirrorUnavailable(
                "--transport rest needs FLYWHEEL_BASE_URL and FLYWHEEL_API_KEY in the "
                "environment (a key held only in the OS keychain is unreadable here — "
                "use the CLI transport for that).")
        return FlywheelRestTransport(run_dir, base, key)

    def version(self) -> str:
        return f"rest {self.base_url}"

    def _request(self, method: str, path: str, *, body: dict | None = None,
                 query: dict | None = None, idempotency_key: str | None = None) -> object:
        import urllib.error  # deferred: keeps the non-mirror path network-module-free
        import urllib.parse
        import urllib.request

        # the configured base URL ends at /api; the runtime lives under /v1
        url = f"{self.base_url}/v1{path}"
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Derived where a caller can derive it (the artifact path does), random
            # otherwise. Reusing a key with a *different* payload hash is a 409, so a
            # derived key is only safe when it is a function of the payload.
            "Idempotency-Key": idempotency_key or str(core.uuid.uuid4()),
        })
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = resp.read().decode() or "{}"
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                payload = json.loads(exc.read().decode())
                detail = str(payload.get("detail") or "")
            except Exception:
                pass
            message = f"{method} {path}: HTTP {exc.code}" + (f": {detail}" if detail else "")
            if exc.code in (401, 403):
                raise MirrorAuthError(message)
            if exc.code == 409:
                raise MirrorConflict(message)
            if exc.code == 429:
                retry = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    retry = float(retry) if retry else None
                except ValueError:
                    retry = None
                raise MirrorRateLimited(message, retry)
            raise MirrorError(message)
        except urllib.error.URLError as exc:
            raise MirrorUnavailable(f"{method} {path}: {exc.reason}")

    def auth_status(self) -> dict:
        raw = self._request("GET", "/auth/status")
        return raw if isinstance(raw, dict) else {}

    def get_node(self, node_id: str) -> MirrorNode:
        raw = self._request("GET", f"/nodes/{node_id}", query={"projection": "core"})
        return MirrorNode.from_raw(raw, context=f"GET /nodes/{node_id}")

    def children(self, node_id: str):
        after = None
        while True:
            raw = self._request("GET", f"/nodes/{node_id}/children",
                                query={"first": 500, "projection": "core", "after": after})
            if not isinstance(raw, dict):
                raise MirrorError(f"GET /nodes/{node_id}/children: unexpected shape")
            for edge in raw.get("edges") or []:
                node = edge.get("node") if isinstance(edge, dict) else None
                if isinstance(node, dict):
                    yield MirrorNode.from_raw(node, context="children", need_revision=False)
            page = raw.get("page_info") if isinstance(raw.get("page_info"), dict) else {}
            if MirrorNode._bool(page.get("has_next_page")) is not True:
                return
            after = page.get("end_cursor")
            if not after:
                return

    def commit_new(self, *, parent_ids, title, content, summary="",
                   repo_context=None, temp_id=None) -> MirrorNode:
        raw = self._request("POST", "/nodes/commit-new", body={
            "local_temp_node_id": temp_id or f"hypergraph-{core.uuid.uuid4()}",
            "parent_ids": [p for p in parent_ids if p],
            "staged_payload": {"title": title, "content": content, "summary": summary,
                               "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT)},
        })
        return MirrorNode.from_raw(raw, context="POST /nodes/commit-new",
                                   need_revision=False)

    def commit(self, *, node_id, base_revision, title, content, summary="",
               repo_context=None) -> MirrorNode:
        session = f"hypergraph-{core.uuid.uuid4()}"
        self._request("POST", f"/nodes/{node_id}/stage/lease/acquire", body={
            "stage_session_id": session, "base_committed_revision": base_revision})
        try:
            raw = self._request("POST", f"/nodes/{node_id}/commit", body={
                "stage_session_id": session, "base_committed_revision": base_revision,
                "staged_payload": {"title": title, "content": content,
                                   "summary": summary,
                                   "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT)}})
        finally:
            try:
                self._request("POST", f"/nodes/{node_id}/stage/lease/release",
                              body={"stage_session_id": session})
            except MirrorError:
                pass
        return MirrorNode.from_raw(raw, context=f"POST /nodes/{node_id}/commit",
                                   need_revision=False)

    def export_subgraph(self, node_ids, out, *, include_descendants=True,
                        max_nodes=5000) -> Path:
        raw = self._request("POST", "/export", body={
            "node_ids": list(node_ids), "include_descendants": include_descendants,
            "max_nodes": max_nodes})
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
        return out

    def delete_node(self, node_id: str, *, mode: str = "detach_shared") -> None:
        self._request("DELETE", f"/nodes/{node_id}", query={"delete_mode": mode})

    # --- re-parenting ----------------------------------------------------------
    def add_parent(self, *, node_id, parent_id, expected_revision,
                   expected_parent_revision) -> None:
        self._request("POST", f"/nodes/{node_id}/parents/add", body={
            "parent_id": parent_id, "expected_revision": int(expected_revision),
            "expected_parent_revision": int(expected_parent_revision)})

    def remove_parent(self, *, node_id, parent_id, expected_revision,
                      expected_parent_revision) -> None:
        self._request("POST", f"/nodes/{node_id}/parents/remove", body={
            "parent_id": parent_id, "expected_revision": int(expected_revision),
            "expected_parent_revision": int(expected_parent_revision)})

    # --- op 10: tags -----------------------------------------------------------
    def graph_tags(self, root_node_id: str) -> tuple[list[dict], int]:
        raw = self._request("GET", f"/nodes/{root_node_id}",
                            query={"projection": "full"})
        return _parse_graph_tags(raw, context=f"GET /nodes/{root_node_id} (full)")

    def create_tag(self, *, root_node_id: str, name: str, expected_revision: int,
                   bg_color: str, text_color: str, one_only: bool = False,
                   track_history: bool = False) -> dict:
        # As on the CLI transport: the response is not trusted for identity. The
        # caller re-reads the root and resolves the new tag by name.
        raw = self._request("POST", f"/nodes/{root_node_id}/tags", body={
            "name": name, "expected_revision": int(expected_revision),
            "bg_color": bg_color, "text_color": text_color,
            "one_only": bool(one_only), "track_history": bool(track_history)})
        return raw if isinstance(raw, dict) else {}

    def assign_tags(self, *, node_id: str, tag_ids: list[str],
                    expected_revision: int) -> None:
        self._request("PUT", f"/nodes/{node_id}/tags", body={
            "tag_ids": list(tag_ids), "expected_revision": int(expected_revision)})

    # --- op 9: artifacts -------------------------------------------------------
    def artifacts(self, node_id: str) -> tuple[list[dict], int]:
        records: list[dict] = []
        revision = 0
        offset = 0
        while True:
            raw = self._request("GET", f"/nodes/{node_id}/artifacts",
                                query={"limit": 100, "offset": offset})
            page, revision, has_more, offset = _parse_artifact_list(
                raw, context=f"GET /nodes/{node_id}/artifacts", offset=offset)
            records += page
            if not has_more:
                return records, revision

    def _put_raw(self, url: str, path: Path, media_type: str) -> int:
        """The signed PUT to the object store. **Deliberately not `_request`.**

        That URL belongs to an external host, not to Flywheel, so `_request` would do
        two wrong things at once: send our `Authorization: Bearer …` credential to a
        third party, and stamp `Content-Type: application/json` onto bytes that are a
        PNG. Raw bytes only — wrapping them in a JSON envelope is a contract
        violation, not a stylistic difference.

        `202` is a success here (`accepted_and_staged`), not a "try again"."""
        import os  # deferred, matching the rest of this file's os usage
        import urllib.error
        import urllib.request

        path = Path(path)
        before = os.stat(path).st_size
        data = path.read_bytes()
        # Re-stat after reading: a run still writing its log would otherwise upload a
        # prefix under a title whose digest describes bytes nobody holds.
        if len(data) != before or os.stat(path).st_size != before:
            raise MirrorError(
                f"{path}: the file changed while it was being read. Refusing to "
                "upload a half-written artifact — the digest in its title would "
                "describe bytes that never existed.")
        req = urllib.request.Request(
            url, data=data, method="PUT",
            headers={"Content-Type": media_type or "application/octet-stream",
                     "Content-Length": str(len(data))})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                code = int(getattr(resp, "status", None) or resp.getcode() or 0)
        except urllib.error.HTTPError as exc:
            raise MirrorError(f"PUT {path.name}: HTTP {exc.code}")
        except urllib.error.URLError as exc:
            raise MirrorUnavailable(f"PUT {path.name}: {exc.reason}")
        if code not in (200, 201, 202):
            raise MirrorError(f"PUT {path.name}: unexpected status {code}")
        return code

    def upload_artifacts(self, *, node_id: str, expected_revision: int,
                         items: list[dict]) -> object:
        """prepare → raw PUT per item → finalize, by hand.

        The CLI does all three inside one process; over REST they are ours to
        sequence, which is why `_put_raw` exists at all."""
        batch = hashlib.sha256(
            "\n".join(str(i.get("title") or "") for i in items).encode()).hexdigest()
        key = hashlib.sha256(f"{node_id}:{batch}".encode()).hexdigest()
        prepared = self._request(
            "POST", f"/nodes/{node_id}/artifacts/prepare",
            idempotency_key=key,
            body={"expected_revision": int(expected_revision),
                  "items": [{k: v for k, v in item.items() if k != "local_path"}
                            for item in items]})
        if not isinstance(prepared, dict):
            raise MirrorError("artifacts prepare: expected an object")
        slots = [s for s in (prepared.get("items") or []) if isinstance(s, dict)]
        if len(slots) != len(items):
            raise MirrorError(
                f"artifacts prepare: {len(slots)} upload slot(s) for {len(items)} "
                "item(s). Refusing to guess which file goes where.")
        for item, slot in zip(items, slots):
            url = str(slot.get("upload_url") or slot.get("url") or "")
            if not url:
                raise MirrorError(
                    f"artifacts prepare: no upload url for {item.get('title')!r}")
            self._put_raw(url, Path(item["local_path"]), str(item.get("media_type") or ""))
        return self._request(
            "POST", f"/nodes/{node_id}/artifacts/finalize", idempotency_key=key,
            body={"upload_id": prepared.get("upload_id"),
                  "expected_revision": int(expected_revision)})


def make_transport(config: dict, *, run_dir: Path, prefer: str = "auto"):
    """The single injection seam. Tests monkeypatch this, nothing else."""
    profile = str((config.get("mirror_profile") or "")) or None
    if prefer == "rest":
        return FlywheelRestTransport.from_env(run_dir)
    if prefer == "cli":
        if not FlywheelCliTransport.available():
            raise MirrorUnavailable(
                f"`{MIRROR_CLI_BINARY}` is not on PATH (npm i -g @paradigma-inc/flywheel).")
        return FlywheelCliTransport(run_dir, env_profile=profile)
    if FlywheelCliTransport.available():
        return FlywheelCliTransport(run_dir, env_profile=profile)
    return FlywheelRestTransport.from_env(run_dir)


# ---------------------------------------------------------------- crash journal

class PushJournal:
    """Local idempotency for mirror writes.

    Duplicate mirror nodes are the only unrecoverable failure in this feature
    (backend/local-adapter.md: duplicates cannot be cleanly merged), and the CLI
    transport cannot inject an Idempotency-Key header — so idempotency is owned
    here. An *intent* is written and fsynced **before** each request, a `done`
    after it. On the next run, any intent without a `done` is resolved **by
    looking**: page the intended parent's children and match title + body sha256.
    Blind retry is never an option."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, entry: dict) -> None:
        import os  # deferred: only the mirror path fsyncs
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                out.append(entry)
        return out

    def intent(self, op: dict, *, parent_id: str | None) -> str:
        intent_id = str(core.uuid.uuid4())
        self._append({"t": "intent", "id": intent_id, "op": op["op"],
                      "slug": op["slug"], "graph": op["graph"], "title": op["title"],
                      "content_sha256": op["content_sha256"], "parent_id": parent_id,
                      "flywheel_node_id": op.get("flywheel_node_id"),
                      "at": core.utc_now()})
        return intent_id

    def done(self, intent_id: str, *, slug: str, node: MirrorNode,
             content_sha256: str) -> None:
        self._append({"t": "done", "id": intent_id, "slug": slug,
                      "flywheel": {"node_id": node.node_id, "slug_name": node.slug,
                                   "revision": node.revision},
                      "content_sha256": content_sha256, "pushed_at": core.utc_now()})

    def artifact_intent(self, *, slug: str, graph: str, node_id: str,
                        items: list[dict]) -> str:
        """One artifact **batch**, recorded before the request. Guard B.

        `push_tags` needs no journal at all — a tag create is idempotent by name, so
        a crashed run finds the tag and adopts it. An artifact upload is an append
        that duplicates, so it needs one. That single difference is the whole design
        in a line.

        The full items go in, not just their titles: recovery has to rebuild the same
        `flywheel.artifacts` entries the normal path would have written."""
        intent_id = str(core.uuid.uuid4())
        self._append({"t": "intent", "id": intent_id, "op": "artifacts",
                      "slug": slug, "graph": graph, "flywheel_node_id": node_id,
                      "items": [dict(i) for i in items], "at": core.utc_now()})
        return intent_id

    def parents_intent(self, *, slug: str, graph: str, node_id: str,
                       add: list[str], remove: list[str]) -> str:
        """One node's whole edge move, recorded before the first `nodes:add-parent`.

        Not for idempotency — an add and a remove are both **idempotent by inspection**
        (the next run's export shows the edge present or absent, and re-derives the
        move from that), so nothing here has to resolve a pending one. It is recorded
        because a crash *between* the add and the remove leaves the node with two
        parents, which is a valid graph that nobody asked for: add-before-remove buys
        "never momentarily parentless" at the price of "momentarily double-parented".
        This line is what tells the operator which of the two windows they landed in."""
        intent_id = str(core.uuid.uuid4())
        self._append({"t": "intent", "id": intent_id, "op": "parents",
                      "slug": slug, "graph": graph, "flywheel_node_id": node_id,
                      "add": list(add), "remove": list(remove), "at": core.utc_now()})
        return intent_id

    def parents_done(self, intent_id: str, *, slug: str, node_id: str,
                     revision: object, parents: list[str]) -> None:
        self._append({"t": "done", "id": intent_id, "slug": slug, "op": "parents",
                      "flywheel": {"node_id": node_id, "revision": revision},
                      "parents": list(parents), "pushed_at": core.utc_now()})

    def artifact_done(self, intent_id: str, *, slug: str, node_id: str,
                      revision: object, attached: list[dict]) -> None:
        self._append({"t": "done", "id": intent_id, "slug": slug, "op": "artifacts",
                      "flywheel": {"node_id": node_id, "revision": revision},
                      "artifacts": [dict(a) for a in attached],
                      "pushed_at": core.utc_now()})

    def abandon(self, intent_id: str, reason: str) -> None:
        """The intended write demonstrably never landed; it is safe to replan."""
        self._append({"t": "abandoned", "id": intent_id, "reason": reason,
                      "at": core.utc_now()})

    def pending(self) -> list[dict]:
        settled = {e["id"] for e in self.entries()
                   if e.get("t") in ("done", "abandoned") and e.get("id")}
        return [e for e in self.entries()
                if e.get("t") == "intent" and e.get("id") not in settled]

    def results(self) -> list[dict]:
        """Exactly the shape `apply_push_results` already eats."""
        out = []
        for e in self.entries():
            if e.get("t") != "done" or not e.get("slug"):
                continue
            entry = {"slug": e["slug"], "flywheel": e["flywheel"],
                     "content_sha256": e.get("content_sha256"),
                     "pushed_at": e.get("pushed_at")}
            if e.get("artifacts") is not None:
                entry["artifacts"] = e["artifacts"]
            out.append(entry)
        return out

    def resolve_artifact_intent(self, entry: dict, transport, *, out=print) -> int:
        """Resolve one crashed artifact batch **by looking**, never by re-uploading.

        Three outcomes, and the third is the point:

        - every title present → the batch landed; adopt the ids;
        - none present → it never landed; abandon and let the next plan re-issue it;
        - **some present → raise**, naming the node and the titles, leaving the intent
          pending.

        A partial batch cannot be completed safely: a second upload would duplicate
        the half that landed, and nothing here calls `artifacts:delete`. So ambiguity
        is reported, never resolved — the same rule `diff_graphs` applies to two nodes
        claiming one mirror id."""
        node_id = str(entry.get("flywheel_node_id") or "")
        slug = entry.get("slug")
        items = [i for i in (entry.get("items") or []) if isinstance(i, dict)]
        if not node_id or not items:
            self.abandon(entry["id"], "artifact intent carries no node id or items")
            return 0
        records, _revision = transport.artifacts(node_id)
        by_title = {str(a.get("title") or ""): a for a in records}
        landed = [i for i in items if str(i.get("title") or "") in by_title]
        if not landed:
            self.abandon(entry["id"], "artifact upload never landed")
            out(f"  {slug}: artifact batch never landed — will be replanned")
            return 0
        if len(landed) != len(items):
            missing = [str(i.get("title") or "") for i in items
                       if str(i.get("title") or "") not in by_title]
            raise MirrorError(
                f"{slug}: {len(landed)} of {len(items)} artifact(s) from an "
                f"unfinished batch are attached to {node_id}; missing "
                f"{', '.join(missing[:3])}{'…' if len(missing) > 3 else ''}. Refusing "
                "to guess — re-uploading would duplicate the half that landed, and "
                "nothing here calls `artifacts:delete` to undo it. Inspect the node's "
                "artifacts and settle it by hand; the intent stays pending on purpose.")
        attached = [{"path": str(i.get("path") or ""), "sha256": str(i.get("sha256") or ""),
                     "artifact_id": artifact_id_of(by_title[str(i["title"])]),
                     "uploaded_at": str(by_title[str(i["title"])].get("created_at")
                                        or core.utc_now())}
                    for i in items]
        # The revision is re-read here rather than carried: the fold that follows
        # re-plans anyway, and a stale one would read as drift on the next verify.
        _records, revision = transport.artifacts(node_id)
        self.artifact_done(entry["id"], slug=slug, node_id=node_id, revision=revision,
                           attached=attached)
        out(f"  {slug}: artifact batch had landed ({len(items)} item(s)) — adopted, "
            "not repeated")
        return 1

    def reconcile_pending(self, transport, *, out=print) -> int:
        """Resolve every intent-without-done by looking, never by retrying."""
        pending = self.pending()
        if not pending:
            return 0
        out(f"push: {len(pending)} unfinished write(s) from a previous run — resolving "
            "by inspection")
        resolved = 0
        for entry in pending:
            slug = entry.get("slug")
            if entry.get("op") == "artifacts":
                resolved += self.resolve_artifact_intent(entry, transport, out=out)
                continue
            if entry.get("op") == "parents":
                # Nothing to resolve and nothing to adopt: `push_parents` re-derives
                # the move from a fresh export every run, so an interrupted one simply
                # replans. Abandoned *loudly*, because the crash window between the add
                # and the remove leaves a legitimately double-parented node.
                self.abandon(entry["id"], "edge move interrupted; replanned from the export")
                out(f"  {slug}: an edge move was interrupted (add "
                    f"{len(entry.get('add') or [])}, remove {len(entry.get('remove') or [])}) "
                    "— the next export re-derives it")
                continue
            if entry.get("op") == "update":
                node_id = entry.get("flywheel_node_id")
                if not node_id:
                    self.abandon(entry["id"], "update intent carries no node id")
                    continue
                live = transport.get_node(node_id)
                if live.sha256 == entry.get("content_sha256"):
                    self.done(entry["id"], slug=slug, node=live,
                              content_sha256=live.sha256)
                    resolved += 1
                    out(f"  {slug}: update had landed — adopting revision {live.revision}")
                else:
                    self.abandon(entry["id"], "update did not land")
                    out(f"  {slug}: update never landed — will be replanned")
                continue
            parent_id = entry.get("parent_id")
            if not parent_id:
                self.abandon(entry["id"], "create intent carries no parent to search")
                continue
            match = None
            for child in transport.children(parent_id):
                if child.title == entry.get("title") \
                        and child.sha256 == entry.get("content_sha256"):
                    match = child
                    break
            if match is not None:
                # the create landed and we crashed before recording it
                live = transport.get_node(match.node_id)
                self.done(entry["id"], slug=slug, node=live, content_sha256=live.sha256)
                resolved += 1
                out(f"  {slug}: create had landed as {live.node_id} — adopted, not repeated")
            else:
                self.abandon(entry["id"], "create never landed")
                out(f"  {slug}: create never landed — will be replanned")
        return resolved


# ----------------------------------------------------------------------- pacing

class Pacer:
    """A minimum interval between writes, not a token bucket.

    A burst bucket spends itself instantly and then eats 429s; there is exactly one
    writer by protocol, so smoothing strictly dominates bursting. 100/min against
    the host's 120/min ceiling leaves headroom for the legend and lineage writes."""

    def __init__(self, per_minute: float = 100.0, *, sleep=None, clock=None):
        import time  # deferred: nothing off the mirror path needs a clock
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._last: float | None = None

    def wait(self) -> None:
        if self.interval <= 0:
            return
        now = self.clock()
        if self._last is not None:
            gap = self.interval - (now - self._last)
            if gap > 0:
                self.sleep(gap)
        self._last = self.clock()

    def slow_down(self, factor: float = 2.0) -> None:
        """The server disagrees with our model of the budget — believe the server."""
        self.interval = max(self.interval, 0.05) * factor

    def backoff(self, attempt: int, retry_after: float | None) -> float:
        delay = retry_after if retry_after is not None else min(2.0 ** attempt, 60.0)
        delay = min(float(delay), 120.0)
        # deterministic jitter: no Math.random-style nondeterminism in tests
        self.sleep(delay)
        return delay


MIRROR_MAX_ATTEMPTS = 4  # the CLI already retries 3x internally → 12 real requests


def mirror_call(fn, *, pacer: Pacer, what: str, retry_conflict=None, out=print,
                attempts: int = MIRROR_MAX_ATTEMPTS):
    """Run one mirror write with pacing, 429 backoff, and no blind 409 retry.

    `attempts=1` is how an **append** is called, and artifact batches pass it. The
    generalization the tags rule was always an instance of: retry is safe when the
    write is an *atomic replace* (`tags:assign` at worst writes the same set twice)
    and unsafe when it is an append (`artifacts:upload` at worst attaches a second
    copy that nothing can retract). Even a 429 is ambiguous there — the one-shot does
    prepare + PUT + finalize in one process, so from outside, "rate limited" and
    "finalize timed out after landing" look the same."""
    last: Exception | None = None
    attempts = max(1, int(attempts))
    for attempt in range(attempts):
        pacer.wait()
        try:
            return fn()
        except MirrorRateLimited as exc:
            last = exc
            pacer.slow_down()   # believe the server, even when we will not retry
            if attempt == attempts - 1:
                break
            delay = pacer.backoff(attempt, exc.retry_after)
            out(f"  rate limited on {what}; slowing down and retrying in {delay:.0f}s")
        except MirrorConflict as exc:
            # One structured re-read, then abort. Under I3 there is one writer.
            if retry_conflict is not None:
                resolved = retry_conflict(exc)
                if resolved is not None:
                    return resolved
            raise MirrorConflict(
                f"{what}: {exc}. The mirror moved under us, which means a second "
                "writer touched it — SPEC I3 says reconcile is the only writer. "
                "Investigate before re-pushing; local files stay canonical.")
    raise last if last else MirrorError(f"{what}: exhausted retries")

# --------------------------------------------------------------- push executor

def _repo_context_for(node: core.LocalNode) -> dict:
    """`## Repo` lines → the host's repo_context. All six keys, null where unknown."""
    ctx = dict(EMPTY_REPO_CONTEXT)
    for line in node.content.splitlines():
        m = re.match(r"^-\s*(repo|branch|commit):\s*(.+?)\s*$", line)
        if not m:
            continue
        key = {"repo": "repo_url", "branch": "branch_name", "commit": "head_commit_sha"}[m.group(1)]
        value = m.group(2).strip()
        if value and value.lower() not in ("none", "n/a", "-"):
            ctx[key] = value
    return ctx


def execute_push(graph_dir: Path, config: dict, transport, *, journal: PushJournal,
                 pacer: Pacer, batch: int = 20, limit: int | None = None,
                 dry_run: bool = False, do_legend: bool = True, do_tags: bool = True,
                 do_artifacts: bool = True, do_parents: bool = True,
                 repo: Path | str | None = None, out=print) -> dict:
    """Plan → execute → fold, resumable at every point.

    `push_plan()` is a pure diff against each file's `flywheel:` frontmatter, so it
    *is* the idempotent resume primitive: everything already stamped is invisible to
    the next plan. Nothing here reimplements it."""
    roots = core.mirror_root_ids(config)

    # 1. resolve anything a previous run left ambiguous, before planning new work
    if journal.reconcile_pending(transport, out=out):
        applied = core.apply_push_results(graph_dir, journal.results())
        out(f"push: folded {applied} recovered write(s) into the node files")

    # 2. plan *after* the fold — the fold changed what the plan is a diff against
    plan = core.push_plan(graph_dir, do_tags=do_tags, do_artifacts=do_artifacts,
                     do_parents=do_parents, repo=repo)
    if plan["violations"]:
        for violation in plan["violations"]:
            out(f"VIOLATION {violation}")
        raise MirrorError(
            "refusing to push: the record graph is append-only and the plan carries "
            f"{len(plan['violations'])} change(s) to already-pushed record node(s). "
            "Fix the local edit — a correction is a new child node, not an edit "
            "(SPEC: record nodes are immutable).")

    # A **four-way** split, and none of the later arms is optional: `o["op"] !=
    # "tags"` would sweep artifact and parent ops into the node loop, which would try
    # to commit a body they do not carry. All three run after the node loop and its
    # result fold, so a node created in this same run already carries its mirror id.
    all_ops = plan["ops"]
    ops = [o for o in all_ops if o["op"] in ("create", "update")]
    parent_ops = [o for o in all_ops if o["op"] == "parents"]
    tag_ops = [o for o in all_ops if o["op"] == "tags"]
    artifact_ops = [o for o in all_ops if o["op"] == "artifacts"]
    if limit is not None:
        ops = ops[:limit]
    creates = sum(1 for o in ops if o["op"] == "create")
    out(f"push: {creates} create(s), {len(ops) - creates} update(s)"
        + (f", {len(parent_ops)} parent set(s)" if parent_ops else "")
        + (f", {len(tag_ops)} tag assignment(s)" if tag_ops else "")
        + (f", {len(artifact_ops)} artifact upload(s)" if artifact_ops else ""))
    if not ops and not parent_ops and not tag_ops and not artifact_ops:
        out("push: mirror already matches the node files — nothing to do")
        return {"created": 0, "updated": 0, "ops": 0, "tagged": 0, "artifacts": 0,
                "reparented": 0, "artifact_problems": []}

    if dry_run:
        for op in all_ops:
            detail = ""
            if op["op"] == "tags":
                detail = f"   [{', '.join(op['tags'])}]"
            elif op["op"] == "artifacts":
                detail = f"   [{len(op['artifacts'])} file(s)]"
            elif op["op"] == "parents":
                # "planned" and not "would": the export `push_parents` takes is the
                # authority, and it routinely reduces one of these to a pure stamp.
                detail = (f"   [planned +{len(op['add'])}/-{len(op['remove'])}, "
                          f"→ {', '.join(op['parent_slugs']) or 'root'}]")
            out(f"  would {op['op']:9} {op['graph']:6} {op['slug']}{detail}")
        return {"created": creates, "updated": len(ops) - creates, "ops": len(ops),
                "tagged": len(tag_ops), "artifacts": len(artifact_ops),
                "reparented": len(parent_ops), "artifact_problems": [],
                "dry_run": True}

    nodes = {}
    for kind in core.GRAPH_KINDS:
        nodes.update(core.load_local_nodes(graph_dir, kind, missing_ok=True))

    minted: dict[str, str] = {}   # local slug → mirror node_id, for null-parent substitution
    pending_results: list[dict] = []
    created = updated = 0

    def settled(node: MirrorNode, what: str) -> MirrorNode:
        """A write's response may omit the revision; read the live one rather than
        stamp a guess. `revision: 0` is real, so a default would poison every later
        update with a permanent conflict."""
        if node.revision is None:
            node = transport.get_node(node.node_id)
        if node.revision is None:
            raise MirrorError(
                f"{what}: the mirror never reported a revision for {node.node_id} — "
                "refusing to stamp a guess into the node file")
        return node

    def flush() -> None:
        nonlocal pending_results
        if not pending_results:
            return
        core.apply_push_results(graph_dir, pending_results, nodes=nodes)
        out(f"  recorded {len(pending_results)} result(s) into the node files")
        pending_results = []

    for op in ops:
        slug = op["slug"]
        local = nodes.get(slug)
        repo_ctx = _repo_context_for(local) if local is not None else None

        if op["op"] == "create":
            parent_ids = []
            for parent_slug, parent_id in zip(op["parent_slugs"], op["parent_flywheel_ids"]):
                if parent_id:
                    parent_ids.append(str(parent_id))
                    continue
                # push_plan orders parents first, so the minted id must already exist
                substituted = minted.get(parent_slug)
                if not substituted:
                    raise MirrorError(
                        f"{slug}: parent `{parent_slug}` has no mirror id yet. The plan "
                        "is ordered parents-first, so this cannot happen — refusing to "
                        "guess a parent and silently reshape the mirror.")
                parent_ids.append(substituted)
            if not parent_ids:
                parent_ids = [roots[op["graph"]]]   # a local root hangs off the mirror root

            intent = journal.intent(op, parent_id=parent_ids[0])
            node = mirror_call(
                lambda: transport.commit_new(
                    parent_ids=parent_ids, title=op["title"], content=op["content"],
                    summary=op["summary"], repo_context=repo_ctx),
                pacer=pacer, what=f"create {slug}", out=out)
            node = settled(node, f"create {slug}")
            journal.done(intent, slug=slug, node=node, content_sha256=op["content_sha256"])
            minted[slug] = node.node_id
            created += 1
            # A create *is* the node's first edge write, so it stamps topology too.
            # Without this the very next plan would schedule an edge move for a node
            # whose edges this call had just made correctly.
            created_parents = [p for p in parent_ids if p not in roots.values()]
        else:
            node_id = str(op["flywheel_node_id"])
            base = op.get("base_revision")
            if base is None:
                # imported graphs carry no revision — read the live one, never assume 0
                base = transport.get_node(node_id).revision
            intent = journal.intent(op, parent_id=None)

            def _resolved(_exc, _op=op, _node_id=node_id):
                live = transport.get_node(_node_id)
                return live if live.sha256 == _op["content_sha256"] else None

            node = mirror_call(
                lambda: transport.commit(
                    node_id=node_id, base_revision=int(base), title=op["title"],
                    content=op["content"], summary=op["summary"], repo_context=repo_ctx),
                pacer=pacer, what=f"update {slug}", retry_conflict=_resolved, out=out)
            node = settled(node, f"update {slug}")
            journal.done(intent, slug=slug, node=node, content_sha256=op["content_sha256"])
            updated += 1

        result = {"slug": slug,
                  "flywheel": {"node_id": node.node_id, "slug_name": node.slug,
                               "revision": node.revision},
                  "content_sha256": op["content_sha256"]}
        # **Only a node that has parents is stamped.** An empty set hashes to a
        # perfectly stable value, and stamping a root with it would make "root, as
        # designed" indistinguishable from "parents cleared locally" — which is
        # precisely what the `(stamp and not node.parents)` arm of the plan reads as a
        # move. The tag stamp gets this for free by never being written on a create.
        if op["op"] == "create" and op["parent_slugs"]:
            result["parents_sha256"] = op["parents_sha256"]
            result["parents"] = created_parents
        pending_results.append(result)
        if len(pending_results) >= batch:
            flush()
    flush()

    # **Parents before tags.** An edge change bumps the child's committed revision and
    # a tag assignment locks against the revision in frontmatter, so the other order
    # would make every re-parented node's assignment conflict on its first attempt.
    reparented = 0
    if parent_ops:
        reparented = push_parents(graph_dir, config, roots, transport,
                                  journal=journal, pacer=pacer, ops=parent_ops, out=out)

    tagged = 0
    if tag_ops:
        tagged = push_tags(graph_dir, config, roots, transport, pacer=pacer, out=out)
    # **Artifacts after tags, before the legend.** `tags:create` bumps the committed
    # revision of *every* node in the graph while an artifact finalize bumps exactly
    # one, so whichever of the two runs second invalidates the other's stamps. Only
    # artifacts are immune, because their `expected_revision` comes from a listing
    # taken microseconds earlier rather than from frontmatter — so putting the immune
    # phase last means no third resync sweep has to exist at all.
    artifacts = {"uploaded": 0, "problems": []}
    if artifact_ops:
        artifacts = push_artifacts(
            graph_dir, config, roots, transport, journal=journal, pacer=pacer,
            repo=Path(repo) if repo is not None else core.repo_root_for({}, graph_dir),
            ops=artifact_ops, out=out)
    if do_legend:
        push_legend(graph_dir, roots["record"], transport, pacer=pacer, out=out)
    return {"created": created, "updated": updated, "ops": len(ops), "tagged": tagged,
            "artifacts": artifacts["uploaded"], "reparented": reparented,
            "artifact_problems": artifacts["problems"]}


def push_legend(graph_dir: Path, record_root_id: str, transport, *, pacer: Pacer,
                out=print) -> str:
    """Create or update the mirror-only slug legend under the mirror record root.

    Two traps, both closed here: children are paged to exhaustion (a root with more
    than one page silently misses the legend and creates a second one on every push,
    which is a duplicate-node generator), and the body hash decides whether the
    write happens at all."""
    body = core.legend_content(graph_dir)
    existing = None
    for child in transport.children(record_root_id):
        if child.title == core.LEGEND_TITLE:
            existing = child
            break
    if existing is None:
        mirror_call(lambda: transport.commit_new(
            parent_ids=[record_root_id], title=core.LEGEND_TITLE, content=body,
            summary="Mirror-only: maps local slugs to the slugs this mirror minted."),
            pacer=pacer, what="create legend", out=out)
        out("  legend: created")
        return "created"
    live = transport.get_node(existing.node_id)
    if live.sha256 == core.body_sha256(body):
        out("  legend: unchanged")
        return "unchanged"
    mirror_call(lambda: transport.commit(
        node_id=live.node_id, base_revision=live.revision, title=core.LEGEND_TITLE,
        content=body,
        summary="Mirror-only: maps local slugs to the slugs this mirror minted."),
        pacer=pacer, what="update legend", out=out)
    out("  legend: updated")
    return "updated"


# Some backends constrain *where* a tag may live, not merely that it exists. Flywheel
# requires a `cluster:*` tag to cover a **connected** set of nodes, and checks it on
# every assignment — so a tag whose final set is perfectly connected is still rejected
# part-way through, because an atomic per-node replace builds that set one node at a
# time. Assignment *order* is therefore part of the contract rather than a detail
# [rec: the neural-whoop field run].
#
# The prefix is a host rule, so it is named here rather than inferred, and a
# `connected:` key in tags.yml overrides it either way for a backend that decides
# differently.
CONNECTED_TAG_PREFIXES = ("cluster:",)


def connectivity_constrained(name: str, entry: dict | None = None) -> bool:
    if entry is not None and entry.get("connected") is not None:
        return bool(entry["connected"])
    return any(name.startswith(prefix) for prefix in CONNECTED_TAG_PREFIXES)


def assignment_order(pending: list, adjacency: dict, constrained: set,
                     already: dict | None = None) -> tuple[list, list]:
    """Order assignments so no constrained tag is ever momentarily split in two.

    → (ordered, blocked). A node is *safe* when, for every constrained tag it carries,
    that tag's already-assigned set is either empty or adjacent to this node. Growing
    each set outward from a single seed is a spanning-tree traversal, so a set that is
    connected at the end can always be built connected; the only real work is
    respecting several tags at once.

    `already` seeds the state from what the mirror currently holds, which is what makes
    this correct after a partial run rather than only on a clean graph."""
    assigned: dict[str, set] = {name: set(slugs) for name, slugs in (already or {}).items()}
    remaining = list(pending)
    ordered: list = []
    while remaining:
        progressed = False
        for i, node in enumerate(remaining):
            tags = [t for t in node.tags if t in constrained]
            if all(not assigned.get(t) or (adjacency.get(node.slug, set()) & assigned[t])
                   for t in tags):
                for t in tags:
                    assigned.setdefault(t, set()).add(node.slug)
                ordered.append(remaining.pop(i))
                progressed = True
                break
        if not progressed:
            # Never silently reorder past it: the host would reject the write anyway,
            # and a caller that cannot see which tag is unsatisfiable cannot fix it.
            return ordered, remaining
    return ordered, []


def reconcile_tag_vocabulary(kind: str, root_id: str, wanted: list[dict], transport, *,
                             pacer: Pacer, vocab: dict, tags_path: Path,
                             out=print) -> tuple[dict[str, str], list[str], int]:
    """Make the mirror root's vocabulary hold every wanted name. → ({name: tag_id}, notes)

    **Resolve by name first, always.** A duplicate tag definition is the one
    unrecoverable failure here, exactly as a duplicate node is: `tags:delete` un-tags
    every node that used the tag, so there is no clean retraction. Every guard in this
    function — the committed `tags.yml`, the name lookup, the re-read below — exists
    for that one reason.

    Idempotent by inspection, with no journal. That is the whole reason to resolve by
    name: a crashed run leaves a tag that the next run *finds* rather than repeats."""
    live, root_revision = transport.graph_tags(root_id)
    by_name = {str(t.get("name") or ""): t for t in live}
    notes: list[str] = []
    ids: dict[str, str] = {}
    created = 0

    for entry in wanted:
        name = str(entry["name"])
        found = by_name.get(name)
        if found is not None:
            ids[name] = str(found.get("tag_id") or "")
            # Reported, never repaired. `tags:update` would rewrite a definition
            # someone may have deliberately restyled on the host, and no invariant
            # reads a colour or a flag.
            for key in ("bg_color", "text_color"):
                mine, theirs = entry.get(key), found.get(key)
                if mine and theirs and str(mine).upper() != str(theirs).upper():
                    notes.append(f"{name}: {key} differs (local {mine}, mirror {theirs})")
            for key in ("one_only", "track_history"):
                mine, theirs = entry.get(key), found.get(key)
                if mine is not None and theirs is not None and bool(mine) != bool(theirs):
                    notes.append(f"{name}: {key} differs (local {bool(mine)}, "
                                 f"mirror {bool(theirs)})")
            continue
        mirror_call(
            lambda entry=entry, rev=root_revision: transport.create_tag(
                root_node_id=root_id, name=str(entry["name"]),
                expected_revision=int(rev),
                bg_color=str(entry.get("bg_color") or core.synth_tag(str(entry["name"]))["bg_color"]),
                text_color=str(entry.get("text_color") or core.synth_tag(str(entry["name"]))["text_color"]),
                one_only=bool(entry.get("one_only")),
                track_history=bool(entry.get("track_history"))),
            pacer=pacer, what=f"create tag {name}", out=out)
        # **Never compute the next root revision, and never take the id from the
        # create's response.** Each create bumps the revision, and the live host
        # returns the updated *root node* here rather than the tag — so both facts
        # come from one authoritative re-read, resolved by name.
        live, root_revision = transport.graph_tags(root_id)
        by_name = {str(t.get("name") or ""): t for t in live}
        made = tag_by_name(live, name)
        if made is None or not made.get("tag_id"):
            raise MirrorError(
                f"create tag {name}: the tag is not on root {root_id} after the "
                "create, so the write did not land. Refusing to continue — the next "
                "step would assign an id that does not exist.")
        ids[name] = str(made["tag_id"])
        # Written after *each* create, not at the end: a crash between two creates
        # must leave the first one recorded, or the next run creates it twice.
        core.merge_tag_def(vocab, kind, {"name": name, "flywheel": {
            "tag_id": ids[name], "root_node_id": root_id, "pushed_at": core.utc_now()}})
        core.write_tag_vocab(tags_path, vocab)
        created += 1
        out(f"  tag: created `{name}` ({ids[name]})")
    return ids, notes, created


def live_tag_assignments(graph_dir: Path, root_id: str, transport,
                         nodes: dict) -> dict[str, set]:
    """{tag name: {local slug}} as the mirror currently holds it.

    Read through one subgraph export rather than per node: the assignment state is
    only needed when a connectivity-constrained tag exists, and then it is needed for
    the whole graph at once."""
    cache = Path(config_cache_dir(graph_dir))
    export = transport.export_subgraph([root_id], cache / "tag-state.json")
    data = json.loads(Path(export).read_text())
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    by_id = {str((n.meta.get("flywheel") or {}).get("node_id") or ""): slug
             for slug, n in nodes.items()}
    names = {t["tag_id"]: str(t.get("name") or "")
             for n in raw_nodes if isinstance(n, dict)
             for t in (n.get("graph_tags") or []) if isinstance(t, dict) and t.get("tag_id")}
    out: dict[str, set] = {}
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        slug = by_id.get(str(raw.get("node_id") or ""))
        if not slug:
            continue
        for tid in (raw.get("tag_ids") or []):
            name = names.get(str(tid))
            if name:
                out.setdefault(name, set()).add(slug)
    return out


def config_cache_dir(graph_dir: Path) -> Path:
    path = Path(graph_dir).parent / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resync_mirror_revisions(graph_dir: Path, roots: dict, transport, *, out=print) -> int:
    """Re-stamp `flywheel.revision` wherever the mirror has moved underneath us.

    **Creating a tag bumps the committed revision of every node in the graph** — not
    only the root, and not only the nodes you go on to assign. Measured on a 196-node
    mirror: 22 creations moved all 196. So after a tag push every stamped revision is
    stale graph-wide, and `verify` (which calls revision skew drift, rightly) would
    report every *untagged* node as drifted forever.

    One export per root answers it for the whole graph. Only the revision is touched:
    body hashes and tag stamps are left alone, so genuine content drift still
    surfaces rather than being papered over."""
    live: dict[str, int] = {}
    cache = config_cache_dir(graph_dir)
    for kind, root_id in roots.items():
        export = transport.export_subgraph([root_id], cache / f"revision-sync-{kind}.json")
        live.update(export_revisions(export))
    return restamp_revisions(graph_dir, live, out=out)


def export_revisions(path_or_data: object) -> dict[str, int]:
    """{mirror node_id: committed revision} out of an export."""
    if isinstance(path_or_data, (str, Path)):
        data = json.loads(Path(path_or_data).read_text())
    else:
        data = path_or_data
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    live: dict[str, int] = {}
    for raw in raw_nodes or []:
        if not isinstance(raw, dict):
            continue
        revision = raw.get("committed_revision", raw.get("revision"))
        node_id = str(raw.get("node_id") or "")
        if node_id and revision is not None:
            live[node_id] = int(revision)
    return live


def restamp_revisions(graph_dir: Path, live: dict[str, int], *, out=print) -> int:
    """Write the mirror's current revisions into `flywheel.revision`. Revision only."""
    restamped = 0
    for kind in core.GRAPH_KINDS:
        for node in core.load_local_nodes(graph_dir, kind, missing_ok=True).values():
            fw = dict(node.meta.get("flywheel") or {})
            node_id = str(fw.get("node_id") or "")
            if not node_id or node_id not in live:
                continue
            if fw.get("revision") is not None and int(fw["revision"]) == live[node_id]:
                continue
            fw["revision"] = live[node_id]
            meta = dict(node.meta)
            meta["flywheel"] = fw
            node.path.write_text(core.render_node_file(meta, node.content))
            restamped += 1
    if restamped:
        out(f"  re-stamped `flywheel.revision` on {restamped} node file(s) — a node's "
            "revision moves when a tag is created, without that node being written")
    return restamped


def push_parents(graph_dir: Path, config: dict, roots: dict, transport, *,
                 journal: PushJournal, pacer: Pacer, ops: list[dict],
                 out=print) -> int:
    """Bring the mirror's parent edges in line with the node files.

    **The one phase that cannot plan offline.** Measured against the installed CLI
    (0.1.108): `nodes:get` reports `has_parents` and **no parent ids at any
    projection** — core or full. So what the mirror actually holds is only knowable
    from an *export*, and this takes exactly one, the same call `push --verify` makes.
    `push_plan`'s `add`/`remove` are the intent, derived from the `flywheel.parents`
    bookkeeping; the export is the authority, and the two are re-diffed here before a
    single edge is touched.

    That is also what makes this feature's **first run** safe rather than lucky. No
    node carries the bookkeeping yet, so every parented node plans a move — and the
    export shows every one of them already correct, which collapses the whole
    migration into a stamp with zero mirror writes. A stamp seeded from the local set
    instead could not have told "never stamped" apart from "re-parented before
    stamping", and would have written a lie that verify then had to catch.

    Two refusals, both about never making the graph worse than it was:

    - **A node is never left parentless.** Add-before-remove is the ordering
      (backend/flywheel.md), and a move whose desired set is empty, or whose parents
      are not all on the mirror yet, is skipped and reported rather than half-applied.
    - **A mirror-only root edge is never removed.** For an adopted project the local
      roots hang off the configured `mirror_roots`, an edge that exists on the mirror
      by design and has no local counterpart to justify it. Reading it as "not
      desired" would detach the whole graph from its root on the first push.
      **Mirror-*only*** is the load-bearing half, and it is the half this got wrong
      first: a re-homed project — this one included — mirrors into the very roots its
      node files declare, so exempting every configured root by id would refuse to
      detach a node from the graph root and leave it double-parented forever. The live
      canary landed in exactly that state, and `push --verify` is what reported it,
      which is the whole argument for `parents` being in the default field set."""
    nodes: dict[str, core.LocalNode] = {}
    for kind in core.GRAPH_KINDS:
        nodes.update(core.load_local_nodes(graph_dir, kind, missing_ok=True))
    cache_dir = Path(config.get("cache_dir") or core.DEFAULT_CACHE_DIR)
    export = transport.export_subgraph(list(roots.values()),
                                       cache_dir / "mirror-parents.json")
    live = {}
    for node_id, raw in core._load_export_nodes(export).items():
        live[node_id] = (
            set(core._norm_parents(raw.get("parent_ids") or raw.get("parents")
                              or raw.get("incoming_ids"))),
            raw.get("committed_revision", raw.get("revision")))
    mirror_only_roots = {str(r) for r in roots.values()} - {
        str((n.meta.get("flywheel") or {}).get("node_id") or "") for n in nodes.values()}

    def revision_of(node_id: str) -> int:
        """Always re-read, never carried. The add bumps the child, so a revision
        computed once and reused across a batch is stale after the first edge."""
        live_node = transport.get_node(node_id)
        if live_node.revision is None:
            raise MirrorError(
                f"{node_id}: the mirror reported no revision — refusing to guess an "
                "optimistic lock for an edge change")
        return int(live_node.revision)

    results: list[dict] = []
    moved = 0
    for op in ops:
        slug = op["slug"]
        # Read the mirror id from the node file, not from the op: the plan was built
        # before the node loop ran, so a node created in *this* run carries one here
        # and not there. The same reason `push_tags` and `push_artifacts` re-load.
        local = nodes.get(slug)
        node_id = str((local.meta.get("flywheel") or {}).get("node_id") if local else ""
                      or op.get("flywheel_node_id") or "")
        if not node_id:
            out(f"  parents: skipping `{slug}` — not on the mirror yet")
            continue
        if node_id not in live:
            out(f"  parents: skipping `{slug}` — {node_id} is not in the mirror export")
            continue

        desired, unpushed = [], []
        for parent_slug in op["parent_slugs"]:
            parent = nodes.get(parent_slug)
            pid = str((parent.meta.get("flywheel") or {}).get("node_id") if parent else "")
            (desired if pid else unpushed).append(pid or parent_slug)
        if unpushed:
            out(f"  parents: skipping `{slug}` — parent(s) {', '.join(unpushed)} are "
                "not on the mirror yet")
            continue
        if not desired:
            out(f"  parents: skipping `{slug}` — it declares no parent on the mirror, "
                "and nothing here detaches a node from every parent it has")
            continue

        held, _revision = live[node_id]
        add = [p for p in desired if p not in held]
        remove = sorted(p for p in held
                        if p not in desired and p not in mirror_only_roots)
        if not add and not remove:
            # The whole first-run migration lands here: the edges are already right
            # and only the bookkeeping was missing.
            results.append({"slug": slug,
                            "flywheel": {"node_id": node_id,
                                         "revision": live[node_id][1]},
                            "parents_sha256": op["parents_sha256"],
                            "parents": desired})
            continue

        intent = journal.parents_intent(slug=slug, graph=op["graph"], node_id=node_id,
                                        add=add, remove=remove)
        for parent_id in add:
            def _reissue(_exc, _child=node_id, _parent=parent_id):
                """The 409 recipe backend/flywheel.md states: re-read, then retry —
                never blind-retry. Safe here in a way an artifact upload is not: an
                edge is a *set* member, so re-issuing at worst asserts an edge that
                already exists, which is the `tags:assign` property one noun over."""
                transport.add_parent(
                    node_id=_child, parent_id=_parent,
                    expected_revision=revision_of(_child),
                    expected_parent_revision=revision_of(_parent))
                return True
            mirror_call(
                lambda c=node_id, p=parent_id: transport.add_parent(
                    node_id=c, parent_id=p, expected_revision=revision_of(c),
                    expected_parent_revision=revision_of(p)),
                pacer=pacer, what=f"add parent {slug} → {parent_id}",
                retry_conflict=_reissue, out=out)
        for parent_id in remove:
            def _reissue_rm(_exc, _child=node_id, _parent=parent_id):
                transport.remove_parent(
                    node_id=_child, parent_id=_parent,
                    expected_revision=revision_of(_child),
                    expected_parent_revision=revision_of(_parent))
                return True
            mirror_call(
                lambda c=node_id, p=parent_id: transport.remove_parent(
                    node_id=c, parent_id=p, expected_revision=revision_of(c),
                    expected_parent_revision=revision_of(p)),
                pacer=pacer, what=f"remove parent {slug} → {parent_id}",
                retry_conflict=_reissue_rm, out=out)

        revision = revision_of(node_id)
        journal.parents_done(intent, slug=slug, node_id=node_id, revision=revision,
                             parents=desired)
        out(f"  parents: {slug} +{len(add)}/-{len(remove)} → "
            f"{', '.join(op['parent_slugs'])}")
        results.append({"slug": slug,
                        "flywheel": {"node_id": node_id, "revision": revision},
                        "parents_sha256": op["parents_sha256"], "parents": desired})
        moved += 1

    if results:
        # **The revision fold is not optional**, for the reason the tag path spells
        # out: an edge change bumps the child, and `verify_mirror` treats revision skew
        # as a violation, so skipping it leaves one permanent false drift finding per
        # re-parented node.
        core.apply_push_results(graph_dir, results, nodes=nodes)
        stamped = len(results) - moved
        out(f"  parents: {moved} edge move(s)"
            + (f", {stamped} already correct (stamped only)" if stamped else ""))
    return moved


def push_tags(graph_dir: Path, config: dict, roots: dict, transport, *, pacer: Pacer,
              out=print) -> int:
    """Create the vocabulary on the mirror roots, then assign it per node.

    Runs after the node loop and its result fold, so a node created in the same run
    already carries the `flywheel.node_id` an assignment needs."""
    tags_path = core.tags_file_for(config, graph_dir)
    vocab = core.load_tag_vocab(tags_path)
    assigned = created_any = 0

    for kind in core.GRAPH_KINDS:
        nodes = core.load_local_nodes(graph_dir, kind, missing_ok=True)
        used = sorted({name for node in nodes.values() for name in node.tags})
        declared = [dict(e) for e in core.tag_vocab_entries(vocab, kind)]
        known = {str(e["name"]) for e in declared}
        # An undeclared name in use still travels: the vocabulary is optional, and a
        # name with no declaration gets its colour from its own digest.
        wanted = declared + [{"name": n, **core.synth_tag(n)} for n in used if n not in known]
        pending = [node for node in nodes.values()
                   if node.tags or (node.meta.get("flywheel") or {}).get("tags_sha256")]
        if not wanted or not pending:
            continue

        ids, notes, created = reconcile_tag_vocabulary(
            kind, roots[kind], wanted, transport, pacer=pacer, vocab=vocab,
            tags_path=tags_path, out=out)
        created_any += created
        for note in notes:
            out(f"  tag drift (reported, not repaired) {note}")

        if created:
            # **Before assigning, not after.** Creating a tag bumps every node in the
            # graph, so every revision now stamped in frontmatter is stale — and an
            # assignment locks against that revision. Without this, all 188 of them
            # conflict on their first attempt and are re-issued, which doubles the
            # writes and only works at all because an atomic replace may be retried.
            resync_mirror_revisions(graph_dir, roots, transport, out=out)
            nodes = core.load_local_nodes(graph_dir, kind, missing_ok=True)
            pending = [node for node in nodes.values()
                       if node.tags or (node.meta.get("flywheel") or {}).get("tags_sha256")]

        by_name = {str(e["name"]): e for e in core.tag_vocab_entries(vocab, kind)}
        constrained = {n for n in used if connectivity_constrained(n, by_name.get(n))}
        if constrained:
            # One extra read, only when a constrained tag exists: what the mirror
            # already holds is the starting state, and without it a resumed run
            # re-derives an order that was valid from empty and is not valid from here.
            adjacency: dict[str, set] = {}
            for slug, node in nodes.items():
                for parent in node.parents:
                    if parent in nodes:
                        adjacency.setdefault(slug, set()).add(parent)
                        adjacency.setdefault(parent, set()).add(slug)
            already = live_tag_assignments(graph_dir, roots[kind], transport, nodes)
            pending, blocked = assignment_order(pending, adjacency, constrained, already)
            if blocked:
                stuck = sorted({t for node in blocked for t in node.tags if t in constrained})
                raise MirrorError(
                    f"cannot order {len(blocked)} assignment(s) so that "
                    f"{', '.join(stuck)} stay(s) connected at every step. This backend "
                    "requires such a tag to cover a connected set of nodes and checks it "
                    "on every write, so the set has to be grown outward from one node — "
                    "which is impossible if it is disconnected in this graph's topology. "
                    "Check whether those nodes are all present and parented as they were "
                    "on the source graph.")
            out(f"  tags: ordered {len(pending)} assignment(s) to keep "
                f"{len(constrained)} connected tag(s) whole at every step")

        results: list[dict] = []
        for node in pending:
            fw = node.meta.get("flywheel") or {}
            node_id = str(fw.get("node_id") or "")
            if not node_id:
                out(f"  tag: skipping `{node.slug}` — not on the mirror yet")
                continue
            want = core.tags_sha256(node.tags)
            if fw.get("tags_sha256") == want:
                continue
            tag_ids = [ids[name] for name in sorted(node.tags) if ids.get(name)]
            revision = fw.get("revision")
            if revision is None:
                revision = transport.get_node(node_id).revision

            def _reissue(_exc, _node_id=node_id, _tag_ids=tag_ids):
                """The one place the no-blind-retry rule inverts, on purpose.

                `tags:assign` is an **atomic replace**, so re-issuing it cannot
                duplicate anything — the worst case is writing the same set twice.
                A create has no such property and keeps the rule."""
                live = transport.get_node(_node_id)
                if live.revision is None:
                    return None
                transport.assign_tags(node_id=_node_id, tag_ids=_tag_ids,
                                      expected_revision=int(live.revision))
                return True

            mirror_call(
                lambda nid=node_id, tids=tag_ids, rev=revision: transport.assign_tags(
                    node_id=nid, tag_ids=tids, expected_revision=int(rev)),
                pacer=pacer, what=f"assign tags {node.slug}", retry_conflict=_reissue,
                out=out)
            # **The revision fold is not optional.** `tags:assign` bumps the node
            # revision, and `verify_mirror` treats revision skew as a violation — so
            # skipping this leaves one permanent false drift finding per tagged node.
            # Read it back; the mutating response schema is `{}`, so never assume +1.
            live = transport.get_node(node_id)
            if live.revision is None:
                raise MirrorError(
                    f"assign tags {node.slug}: the mirror reported no revision after "
                    "the assignment. Refusing to stamp a guess — an unstamped tag push "
                    "reads as drift on every later verify.")
            results.append({"slug": node.slug,
                            "flywheel": {"node_id": node_id, "slug_name": live.slug,
                                         "revision": live.revision},
                            "content_sha256": node.sha256, "tags_sha256": want})
            assigned += 1
        if results:
            core.apply_push_results(graph_dir, results, nodes=nodes)
            out(f"  tags: assigned on {len(results)} {kind} node(s)")
    if created_any:
        # Once more at the end. The pre-assignment resync covers the graph as it was
        # before this kind's assignments; a second graph (state) creating its own tags
        # afterwards would move the first one's nodes again.
        resync_mirror_revisions(graph_dir, roots, transport, out=out)
    return assigned


def push_artifacts(graph_dir: Path, config: dict, roots: dict, transport, *,
                   journal: PushJournal, pacer: Pacer, repo: Path,
                   ops: list[dict], out=print) -> dict:
    """Upload each record node's declared evidence, once, and fold the bump.

    A sibling of `push_tags` with one structural difference: it takes a **journal**,
    which `push_tags` does not. That difference *is* the design. A tag create is
    idempotent by name — a crashed run finds the tag and adopts it. An artifact
    upload is an append, and a repeated append duplicates. So there are two guards:

    - **Guard A — the listing, always.** Every batch is preceded by one
      `artifacts:list`, which is needed anyway for `expected_revision`, and any item
      whose title is already attached is dropped. In the common case a duplicate
      becomes structurally unreachable, at the cost of a read we already had to make.
      Stronger than the node-create path, which cannot afford a listing per create.
    - **Guard B — the journal**, for the crash window between the request and the
      fold (`resolve_artifact_intent`).

    Pacing is once per **batch**: prepare and finalize are the graph writes. The
    signed PUTs go to object storage and are deliberately unpaced — say so here, or
    somebody will "fix" it later.
    """
    nodes: dict[str, core.LocalNode] = {}
    for kind in core.GRAPH_KINDS:
        nodes.update(core.load_local_nodes(graph_dir, kind, missing_ok=True))
    uploaded = 0
    problems: list[str] = []
    results: list[dict] = []

    for op in ops:
        slug = op["slug"]
        # Read from the node file, not from the op. The plan was built before the node
        # loop ran, so a node created in *this* run carries no mirror id in the plan
        # and does carry one here — the same reason `push_tags` re-loads.
        local = nodes.get(slug)
        node_id = str((local.meta.get("flywheel") or {}).get("node_id") if local else ""
                      or op.get("flywheel_node_id") or "")
        if not node_id:
            out(f"  artifact: skipping `{slug}` — not on the mirror yet")
            continue
        for problem in op.get("problems") or []:
            out(f"ARTIFACT MISSING {slug}: {problem}")
            problems.append(f"{slug}: {problem}")
        refs = list(op.get("artifacts") or [])
        stamped = {str(r.get("path") or "")
                   for r in (((local.meta.get("flywheel") or {}).get("artifacts") or [])
                             if local else []) if isinstance(r, dict)}
        for gone in sorted(stamped - {r["path"] for r in refs}):
            # Nothing is un-attached on the mirror, ever: the only operation that
            # would is `artifacts:delete`, and it destroys bytes. The entry stays in
            # `flywheel.artifacts` and this line says so out loud.
            out(f"  artifact: `{gone}` is no longer declared on `{slug}` — the mirror "
                "copy is left in place (nothing here deletes)")

        records, revision = transport.artifacts(node_id)   # Guard A: dedupe + lock
        attached_titles = {str(a.get("title") or "") for a in records}
        pending = [r for r in refs
                   if core.artifact_title(r["path"], r["sha256"]) not in attached_titles]

        for batch in core.artifact_batches(pending):
            items = [core.artifact_item_for(r["path"], r["sha256"], abs_path=r["abs_path"])
                     for r in batch]
            intent = journal.artifact_intent(
                slug=slug, graph=op["graph"], node_id=node_id,
                items=[{"path": r["path"], "sha256": r["sha256"],
                        "title": core.artifact_title(r["path"], r["sha256"])}
                       for r in batch])
            try:
                mirror_call(
                    lambda nid=node_id, rev=revision, its=items:
                        transport.upload_artifacts(node_id=nid, expected_revision=int(rev),
                                                   items=its),
                    pacer=pacer, what=f"upload artifacts {slug}", out=out, attempts=1)
            except MirrorRateLimited as exc:
                raise MirrorRateLimited(
                    f"upload artifacts {slug}: {exc}. Not retried, on purpose: the "
                    "upload is one process doing prepare + PUT + finalize, so a 429 "
                    "cannot be told apart from a finalize that landed and timed out. "
                    "The pacer has been slowed; the next run resolves this batch by "
                    "listing what is attached.", exc.retry_after)
            except MirrorConflict as exc:
                raise MirrorConflict(
                    f"upload artifacts {slug}: {exc}. Not re-read-and-reissued: the "
                    "tags inversion is a property of *atomic replace*, and an "
                    "artifact upload is an **append**. Appends keep the "
                    "no-blind-retry rule in full — a second one attaches a duplicate "
                    "that nothing here can retract. The next run resolves it by "
                    "listing.")
            # **Never take the id from the upload's own response.** The mutating
            # success schema is `{}`, and `tags:create` famously returns the wrong
            # object entirely. Re-read and resolve by title — `tag_by_name` with a
            # different key, for the identical reason.
            records, revision = transport.artifacts(node_id)
            by_title = {str(a.get("title") or ""): a for a in records}
            landed = []
            for ref in batch:
                title = core.artifact_title(ref["path"], ref["sha256"])
                found = by_title.get(title)
                if found is None:
                    raise MirrorError(
                        f"upload artifacts {slug}: `{title}` is not attached to "
                        f"{node_id} after the upload, so the write did not land. "
                        "Refusing to continue — the next step would stamp an "
                        "artifact id that does not exist.")
                landed.append({"path": ref["path"], "sha256": ref["sha256"],
                               "artifact_id": artifact_id_of(found),
                               "uploaded_at": str(found.get("created_at") or core.utc_now())})
            journal.artifact_done(intent, slug=slug, node_id=node_id,
                                  revision=revision, attached=landed)
            uploaded += len(batch)

        by_title = {str(a.get("title") or ""): a for a in records}
        attached = []
        for ref in refs:
            found = by_title.get(core.artifact_title(ref["path"], ref["sha256"]))
            if found is None:
                continue
            attached.append({"path": ref["path"], "sha256": ref["sha256"],
                             "artifact_id": artifact_id_of(found),
                             "uploaded_at": str(found.get("created_at") or core.utc_now())})
        # **The revision fold happens here, per node, from the listing already
        # performed.** No graph-wide resync sweep: finalize bumps exactly one node,
        # unlike `tags:create`, which moves all of them. The fold is not optional —
        # skipping it leaves one permanent false drift finding per node, which is the
        # 188-findings incident with a different noun.
        entry = {"slug": slug,
                 "flywheel": {"node_id": node_id, "revision": revision},
                 "artifacts": attached}
        if not op.get("problems"):
            entry["artifacts_sha256"] = op.get("artifacts_sha256")
        else:
            # Withheld so the next push retries. What *did* land is still recorded.
            out(f"  artifact: `{slug}` stamp withheld — one or more files could not "
                "be uploaded; the next push retries them")
        results.append(entry)

    if results:
        core.apply_push_results(graph_dir, results, nodes=nodes)
        out(f"  artifacts: {uploaded} file(s) uploaded across {len(results)} node(s)")
    return {"uploaded": uploaded, "problems": problems}


def push_lineage(graph_dir: Path, config: dict, record_root_id: str, transport, *,
                 pacer: Pacer, out=print) -> str:
    """Write the archive-lineage body onto the mirror record root (adopted projects)."""
    body = core.lineage_content(graph_dir, config)
    live = transport.get_node(record_root_id)
    if live.sha256 == core.body_sha256(body):
        out("  lineage: unchanged")
        return "unchanged"
    mirror_call(lambda: transport.commit(
        node_id=record_root_id, base_revision=live.revision, title=live.title,
        content=body, summary=live.summary), pacer=pacer, what="lineage", out=out)
    out("  lineage: updated")
    return "updated"


def verify_against_mirror(graph_dir: Path, config: dict, transport, *,
                          cache_dir: Path, out=print, strict: bool = False) -> core.Report:
    """Export this project's own mirror roots and diff them against the node files."""
    roots = core.mirror_root_ids(config)   # also asserts no archive root is spliced in
    export = transport.export_subgraph(list(roots.values()),
                                       cache_dir / "mirror-verify.json")
    data = json.loads(Path(export).read_text())
    if isinstance(data, dict) and data.get("truncated"):
        raise MirrorError(
            "the mirror export was truncated at max_nodes — every node past the cut "
            "would read as drift. Raise the bound rather than trusting this result.")
    exempt = set(roots.values())
    exempt |= {str(v.get("node_id"))
               for v in (config.get("mirror_roots") or {}).values()
               if isinstance(v, dict) and v.get("node_id")}
    report = core.verify_mirror(graph_dir, export, exempt, strict=strict)
    for finding in report.violations():
        out(f"DRIFT {finding}")
    out(f"push --verify{' --strict' if strict else ''}: "
        f"{len(report.violations())} drift finding(s)")
    return report

# -------------------------------------------------------------- mirror plumbing

def mirror_paths(config: dict, args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """(cache_dir, journal path, transport run dir) — all under the gitignored cache."""
    cache_dir = Path(config.get("cache_dir") or core.DEFAULT_CACHE_DIR)
    journal = Path(getattr(args, "journal", None) or cache_dir / "push-journal.jsonl")
    return cache_dir, journal, cache_dir / "push-run"


def mirror_not_ours(config: dict, transport) -> str | None:
    """→ why this machine cannot publish this project's mirror, or None when it can.

    Distinguishes *a contributor's clone* from *a broken owner setup*. A fork inherits
    the committed `mirror:` key but no credentials for it, and reconcile calls `push`
    unconditionally — so without this the documented workflow exits 2 on every outside
    contributor's machine [rec: vast-rain-4873].
    """
    try:
        status = transport.auth_status()
    except MirrorError as exc:
        return str(exc)
    if not status.get("authenticated"):
        return "not authenticated for this project's mirror"
    expected = str(config.get("mirror_account_id") or "")
    user_id = str(status.get("user_id") or "")
    if expected and user_id and expected != user_id:
        return (f"authenticated as account {user_id}, but this project's mirror belongs "
                f"to {expected} — this clone is not the publisher")
    return None


def mirror_session(config: dict, args: argparse.Namespace):
    """Build (transport, journal, pacer). The one place the mirror path starts."""
    cache_dir, journal_path, run_dir = mirror_paths(config, args)
    transport = make_transport(config, run_dir=run_dir,
                               prefer=getattr(args, "transport", "auto") or "auto")
    pacer = Pacer(float(getattr(args, "rate", None) or 100.0))
    return transport, PushJournal(journal_path), pacer, cache_dir


def run_push(args: argparse.Namespace, config: dict, graph_dir: Path) -> int:
    """The executing tail of `push` — everything that needs a transport.

    Core's `cmd_push` keeps the offline modes and the transport-free stand-down
    gates (no mirror configured, wrong branch): by the time control reaches here a
    mirror is declared and this checkout may publish. The remaining stand-down —
    "not ours" — needs a transport to ask, so it lives on this side."""
    def stand_down(reason: str) -> int:
        if args.require_mirror:
            raise MirrorError(f"{reason} (--require-mirror)")
        print(f"push: {reason} — nothing published")
        return 0

    try:
        transport, journal, pacer, cache_dir = mirror_session(config, args)
        if reason := mirror_not_ours(config, transport):
            return stand_down(reason)
    except (MirrorUnavailable, MirrorAuthError) as exc:
        return stand_down(str(exc))

    if not args.skip_preflight:
        report = mirror_doctor(config, graph_dir, transport, probe_write=False,
                               repo=getattr(args, "repo", None))
        for finding in report.violations():
            print(f"PREFLIGHT {finding}", file=sys.stderr)
        if report.violations():
            raise MirrorError("preflight failed — run `hypergraph mirror doctor` for detail")

    if args.verify:
        report = verify_against_mirror(graph_dir, config, transport, cache_dir=cache_dir,
                                       strict=args.strict)
        return 1 if report.violations() else 0

    if not args.yes and not args.dry_run:
        plan = core.push_plan(graph_dir, do_artifacts=not args.no_artifacts,
                         repo=getattr(args, "repo", None))
        creates = sum(1 for o in plan["ops"] if o["op"] == "create")
        if creates > core.PUSH_CREATE_WARN:
            raise MirrorError(
                f"{creates} creates in one run is above the {core.PUSH_CREATE_WARN} warning "
                "threshold. Re-run with --yes if that is intended, or --limit N to go "
                "in chunks.")
        files = [r for o in plan["ops"] if o["op"] == "artifacts"
                 for r in (o.get("artifacts") or [])]
        size = sum(int(r.get("size") or 0) for r in files)
        if len(files) > core.PUSH_ARTIFACT_WARN:
            raise MirrorError(
                f"{len(files)} artifact files in one run is above the "
                f"{core.PUSH_ARTIFACT_WARN} warning threshold. Re-run with --yes if that "
                "is intended, or --no-artifacts to publish the node bodies first.")
        if size > core.PUSH_ARTIFACT_BYTES_WARN:
            raise MirrorError(
                f"{size // (1024 * 1024)} MiB of artifacts in one run is above the "
                f"{core.PUSH_ARTIFACT_BYTES_WARN // (1024 * 1024)} MiB warning threshold. "
                "Re-run with --yes if that is intended, or --no-artifacts.")

    summary = execute_push(graph_dir, config, transport, journal=journal, pacer=pacer,
                           batch=args.batch, limit=args.limit, dry_run=args.dry_run,
                           do_legend=not args.no_legend, do_tags=not args.no_tags,
                           do_artifacts=not args.no_artifacts,
                           repo=getattr(args, "repo", None))
    if summary.get("dry_run"):
        return 0
    if config.get("archive"):
        push_lineage(graph_dir, config, core.mirror_root_ids(config)["record"], transport,
                     pacer=pacer)
    print(f"push: {summary['created']} created, {summary['updated']} updated"
          + (f", {summary['tagged']} tagged" if summary.get("tagged") else "")
          + (f", {summary['artifacts']} artifact(s) uploaded"
             if summary.get("artifacts") else ""))
    failed_artifacts = list(summary.get("artifact_problems") or [])
    if failed_artifacts:
        # Everything else on those nodes still landed, and the stamp was withheld so
        # the next push retries. Non-zero anyway: an evidence link that points at
        # nothing must not exit 0 into somebody's CI.
        for problem in failed_artifacts:
            print(f"ARTIFACT MISSING {problem}", file=sys.stderr)
    if not args.no_verify:
        report = verify_against_mirror(graph_dir, config, transport, cache_dir=cache_dir)
        # A node's revision can move without that node being written — creating a tag
        # moves every node in the graph. That leaves stamps stale on nodes nothing
        # touched, and no later push would ever fix them, because a push only writes
        # what changed. So converge here, from the export `verify` already fetched:
        # no extra request, only the revision rewritten, and a re-verify to prove it.
        skew = [f for f in report.violations() if f.message.startswith("revision skew")]
        if skew:
            export = cache_dir / "mirror-verify.json"
            if export.exists():
                restamped = restamp_revisions(graph_dir, export_revisions(export))
                if restamped:
                    print(f"push: re-stamped `flywheel.revision` on {restamped} node "
                          "file(s) the mirror had moved underneath us — re-verifying")
                    report = verify_against_mirror(graph_dir, config, transport,
                                                   cache_dir=cache_dir)
        if report.violations():
            return 1
    return 1 if failed_artifacts else 0


# ---------------------------------------------------------------- mirror doctor

def mirror_doctor(config: dict, graph_dir: Path, transport, *,
                  probe_write: bool = True,
                  repo: Path | str | None = None) -> core.Report:
    """Preflight, reported in `check`'s own shape so the output reads the same."""
    report = core.Report()
    if not core.mirror_configured(config):
        report.add("info", "mirror", "-", "no mirror configured — push is a no-op")
        return report

    report.add("info", "mirror", "-", f"transport: {transport.name} ({transport.version()})")

    try:
        status = transport.auth_status()
    except MirrorError as exc:
        report.add("violation", "mirror", "auth", str(exc))
        return report
    if not status.get("authenticated"):
        report.add("violation", "mirror", "auth",
                   "not authenticated — run `flywheel auth:login`")
        return report
    user_id = str(status.get("user_id") or "")
    report.add("info", "mirror", "auth",
               f"authenticated as {user_id or '(unknown user)'} "
               f"via {status.get('auth_method') or '?'}")

    # Account match. This retires an incident that cost two rounds: a mirror that
    # looked deleted and was not — the key simply belonged to a different account.
    expected = str(config.get("mirror_account_id") or "")
    if expected and user_id and expected != user_id:
        report.add("violation", "mirror", "account",
                   f"this key belongs to account {user_id}, but the config's "
                   f"`mirror_account_id:` says {expected}. The mirror is not missing — "
                   "you are looking at it from the wrong account.")
    elif not expected and user_id:
        report.add("warning", "mirror", "account",
                   f"config has no `mirror_account_id:` — add {user_id} so a "
                   "wrong-key run reports the account rather than a missing graph")

    try:
        roots = core.mirror_root_ids(config)
    except MirrorError as exc:
        report.add("violation", "mirror", "roots", str(exc))
        return report
    for kind, node_id in roots.items():
        try:
            node = transport.get_node(node_id)
        except MirrorError as exc:
            report.add("violation", "mirror", f"{kind}-root",
                       f"{node_id} does not resolve: {exc}")
            continue
        report.add("info", "mirror", f"{kind}-root",
                   f"{node.slug or node_id} — {node.title!r} (revision {node.revision})")
        if node.can_write is False:
            report.add("violation", "mirror", f"{kind}-root",
                       "the authenticated key cannot write this root")

    if probe_write:
        # Not optional. A key can authenticate cleanly, list hundreds of nodes and
        # 403 every write; there is no scope introspection, so only a real write
        # detects it. Parentless on purpose — under the mirror record root this
        # probe would immediately show up in `verify` as "no local counterpart".
        # The mirror is not scratch space.
        probe = None
        try:
            probe = transport.commit_new(
                parent_ids=[], title="hypergraph write probe",
                content="Transient probe written by `hypergraph mirror doctor`.\n"
                        "If you are reading this, a probe failed to clean up; "
                        "deleting it is safe.\n",
                summary="transient")
            report.add("info", "mirror", "write-probe",
                       f"write accepted (probe {probe.node_id})")
        except MirrorError as exc:
            report.add("violation", "mirror", "write-probe",
                       f"the key authenticated but cannot write: {exc}")
        finally:
            if probe is not None:
                try:
                    transport.delete_node(probe.node_id)
                    report.add("info", "mirror", "write-probe", "probe deleted")
                except MirrorError as exc:
                    report.add("warning", "mirror", "write-probe",
                               f"probe {probe.node_id} could not be deleted ({exc}) — "
                               "delete it by hand; it is parentless, so nothing else "
                               "points at it")

    if probe_write:
        # Named, not probed. The only cleanup for a test artifact is
        # `artifacts:delete`, which this design refuses to wire at all (it destroys
        # bytes, and nothing local asked for that) — so rather than invent a probe it
        # cannot clean up after, doctor says out loud which surface stays untested.
        report.add("info", "mirror", "artifacts",
                   "no write probe for artifacts: its only cleanup would be "
                   "`artifacts:delete`, which nothing here wires. Artifact write "
                   "scope is a known un-probed surface.")

    try:
        plan = core.push_plan(graph_dir, repo=repo)
    except core.LocalGraphError as exc:
        report.add("violation", "mirror", "plan", str(exc))
        return report
    creates, updates, tags, artifact_ops = core.plan_op_counts(plan)
    report.add("info", "mirror", "plan",
               f"{creates} create(s), {updates} update(s), "
               f"{tags} tag assignment(s), {artifact_ops} artifact upload(s) pending")
    if creates > core.PUSH_CREATE_WARN:
        report.add("warning", "mirror", "plan",
                   f"{creates} creates at 120 writes/min is roughly "
                   f"{creates // 100 + 1} minute(s) of paced writing")
    # Artifact preflight, computed from the plan already in hand — **zero extra
    # requests**. Warnings, never violations: `cmd_push` raises on any doctor
    # violation, and aborting a whole push because one evidence file moved would
    # contradict the per-node failure handling this feature is built around.
    files = 0
    size = 0
    for op in plan["ops"]:
        if op.get("op") != "artifacts":
            continue
        for problem in op.get("problems") or []:
            report.add("warning", "mirror", op["slug"], f"artifact {problem}")
        files += len(op.get("artifacts") or [])
        size += sum(int(r.get("size") or 0) for r in op.get("artifacts") or [])
    if files:
        report.add("info", "mirror", "artifacts",
                   f"{files} artifact file(s), {size // (1024 * 1024)} MiB to upload "
                   f"in batches of {core.ARTIFACT_BATCH_ITEMS}")
    for violation in plan["violations"]:
        report.add("violation", "mirror", "plan", violation)
    return report


def run_mirror(args: argparse.Namespace) -> int:
    """The `mirror` subcommand — diagnostics, roots, pulls. Core's `cmd_mirror` is
    a stub that loads this module: every action here needs a transport."""
    config = core.load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or core.DEFAULT_GRAPH_DIR)

    if args.action == "doctor":
        if not core.mirror_configured(config):
            print("mirror doctor: no mirror configured — `push` is a no-op here")
            return 0
        transport, _journal, _pacer, _cache = mirror_session(config, args)
        report = mirror_doctor(config, graph_dir, transport,
                               probe_write=not args.no_write_probe,
                               repo=getattr(args, "repo", None))
        for finding in report.findings:
            print(f"{finding.level:9} {finding}")
        print(f"\nmirror doctor: {len(report.violations())} violation(s), "
              f"{len(report.warnings())} warning(s)")
        return 1 if report.violations() else 0

    if args.action == "roots":
        if not args.mint:
            roots = core.mirror_root_ids(config)
            for kind, node_id in roots.items():
                print(f"{kind}: {node_id}")
            return 0
        return mint_mirror_roots(config, args)

    if args.action == "pull":
        transport, _journal, _pacer, cache_dir = mirror_session(config, args)
        return mirror_pull(transport, args, out_dir=args.out_dir or cache_dir)

    raise core.LocalGraphError(f"unknown mirror action: {args.action}")


def mint_mirror_roots(config: dict, args: argparse.Namespace) -> int:
    """Mint both mirror roots and append them to the config, idempotently.

    Titles stay plain — `<project> — record` / `<project> — state`. Any lineage
    belongs in the root's body, never in its title (SPEC: a continuing graph is not
    a copy of the graph it forked from)."""
    existing = config.get("mirror_roots") or {}
    if existing and not args.force:
        raise core.LocalGraphError(
            "the config already declares `mirror_roots:` — re-minting would orphan the "
            "existing mirror. Pass --force only if you mean to abandon it.")
    transport, _journal, pacer, _cache = mirror_session(config, args)
    project = str(config.get("project") or "project")
    minted = {}
    for kind in core.GRAPH_KINDS:
        node = mirror_call(lambda kind=kind: transport.commit_new(
            parent_ids=[], title=f"{project} — {kind}",
            content=f"{'Append-only record' if kind == 'record' else 'Distilled state'} "
                    f"graph for {project}.\n\nThis graph is a one-way mirror of the "
                    "markdown node files committed in the repo, which stay canonical.\n",
            summary=f"{kind} graph mirror root for {project}."),
            pacer=pacer, what=f"mint {kind} root")
        minted[kind] = node
        print(f"minted {kind} root: {node.node_id} ({node.slug})")

    if args.config:
        # Surgical append, never a yaml round-trip: safe_dump would destroy 40 of
        # config.example.yml's 68 lines of comments.
        path = Path(args.config)
        text = path.read_text()
        block = ["", "# Mirror roots minted by `hypergraph mirror roots --mint`.",
                 "mirror_roots:"]
        for kind, node in minted.items():
            block += [f"  {kind}:", f"    node_id: {node.node_id}",
                      f"    slug: {node.slug}"]
        path.write_text(text.rstrip("\n") + "\n" + "\n".join(block) + "\n")
        print(f"appended mirror_roots: to {path}")
    return 0


def mirror_pull(transport, args: argparse.Namespace, *, out_dir: Path) -> int:
    """One export over every anchor, split locally into record.json / state.json.

    No `--import` flag: two commands, each inspectable. The split is a BFS from each
    graph's anchors — a node reachable from both is an error, because the two graphs
    are disjoint by construction (SPEC: pointers are markdown, never edges)."""
    record_ids = list(args.record_node_id or []) + list(args.node_id or [])
    state_ids = list(args.state_node_id or [])
    if not record_ids and not state_ids:
        raise core.LocalGraphError(
            "mirror pull needs at least one anchor: --record-node-id and/or "
            "--state-node-id (--node-id is an alias for the record graph)")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = transport.export_subgraph(record_ids + state_ids,
                                         out_dir / "mirror-pull.json")
    data = json.loads(Path(combined).read_text())
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    by_id = {str(n.get("node_id") or n.get("id")): n for n in raw_nodes
             if isinstance(n, dict) and (n.get("node_id") or n.get("id"))}
    children: dict[str, list[str]] = {nid: [] for nid in by_id}
    for nid, raw in by_id.items():
        for parent in (raw.get("incoming_ids") or raw.get("parent_ids") or []):
            if str(parent) in children:
                children[str(parent)].append(nid)

    def reachable(anchors: list[str]) -> set[str]:
        seen, queue = set(), [a for a in anchors if a in by_id]
        while queue:
            nid = queue.pop()
            if nid in seen:
                continue
            seen.add(nid)
            queue.extend(children.get(nid, []))
        return seen

    record_set, state_set = reachable(record_ids), reachable(state_ids)
    overlap = record_set & state_set
    if overlap:
        raise core.LocalGraphError(
            f"{len(overlap)} node(s) are reachable from both the record and state "
            f"anchors (e.g. {sorted(overlap)[0]}). The two graphs must stay disjoint — "
            "check the anchors before importing.")

    for kind, ids in (("record", record_set), ("state", state_set)):
        if not ids:
            continue
        # `legacy-` and not `record.json`: `export` writes `record.json` into this
        # same directory by default, so the pull and the first export collided and
        # the export silently destroyed the legacy graph. Step 7 still needs it —
        # `--resolve-prefixes --against` reads it — and it is the only record of
        # pre-import artifact counts. Found on neural-whoop, recovered by re-pulling.
        path = out_dir / f"legacy-{kind}.json"
        path.write_text(json.dumps(
            {"version": core.EXPORT_VERSION, "graph": kind, "exported_at": core.utc_now(),
             "nodes": [by_id[i] for i in sorted(
                 ids, key=lambda i: (str(by_id[i].get("created_at") or ""), i))]},
            indent=2, ensure_ascii=False))
        print(f"wrote {path} ({len(ids)} node(s))")

    print("\n# Paste into .hypergraph/config.yml if this graph becomes a frozen archive:",
          file=sys.stderr)
    print("archive:\n  backend: flywheel\n  roots:", file=sys.stderr)
    for nid in record_ids + state_ids:
        raw = by_id.get(nid) or {}
        title = str(raw.get("title") or "").replace("'", "''")
        print(f"    - slug: {raw.get('slug_name') or raw.get('slug') or '?'}\n"
              f"      node_id: {nid}\n      title: '{title}'", file=sys.stderr)
    return 0
