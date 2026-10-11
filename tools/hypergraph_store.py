"""The Flywheel local repository as the graphs' canonical store (backend/flywheel-repo-adapter.md).

Loaded lazily by `tools/hypergraph.py` (`_store()`), exactly like the mirror, and only
when `.hypergraph/config.yml` declares

    store:
      kind: flywheel-repo
      flywheel_cli: 0.2.78     # the pinned CLI version; a newer one may upgrade the format

Model. The Flywheel repository at the main checkout's root (`.flywheel/`) is the store
of record. `.hypergraph/graph/` stays exactly what every other command already reads —
one markdown file per node — but becomes a gitignored **working copy** of the store:
the core keeps doing all its validation and file writes, and this module carries the
difference across in both directions.

- `push` (after every writing command, under the store lock): each node file whose
  bytes changed since the index last saw them is staged — created with its slug, title
  and summary, or updated field by field — with its parents mirrored as lineage and
  every non-root node contained under its graph's root, then committed as one
  Flywheel commit.
- `refresh` (before every writing command and `export`): when the store's head has
  moved past the index (another machine's commits arrived by `flywheel repo:pull`),
  the nodes that changed are re-materialized into files.

Encoding. A node's Flywheel `content` is the file's body followed by one trailer,

    <body>\\n<!-- hypergraph:<kind>\\n<the file's frontmatter, verbatim>-->\\n

so the file is rebuilt byte-for-byte from the store alone (frontmatter + body), the
trailer renders invisibly on the hosted graph, and `slug_name`, `title` and `summary`
are also real Flywheel fields. Flywheel mints its own node ids; the protocol's ids
(`uuid5(slug)`) and slugs stay in the frontmatter, which is what `export` reads.

Concurrency. A Flywheel repository has one staging area, so two writers staging at
once sweep each other's operations into the wrong commit. Every stage-and-commit here
holds an exclusive `flock` on `.hypergraph/store/lock` in the main checkout, which git
worktrees share: worktree agents write into the one graph rather than a branch slice.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import hypergraph_core as core  # registered by core's `_store()` before exec

STORE_KIND = "flywheel-repo"
MARKER = "\n<!-- hypergraph:"
CLOSE = "-->\n"
ORIGIN_HOST = "hypergraph"
BATCH_OPS = 400          # ops per Flywheel commit during a bulk import
READ_WORKERS = 8         # parallel `node:get` calls for a full materialization
LOCK_TIMEOUT_S = 600


class StoreError(core.LocalGraphError):
    """A store problem; the CLI turns it into exit 2 like any other graph error."""


# ------------------------------------------------------------------- encoding

def split_file(text: str, where: str) -> tuple[dict, str, str]:
    """→ (meta, head, body): `head` is the frontmatter block verbatim, `head+body == text`."""
    meta, body = core.split_frontmatter(text, where)
    if not text.endswith(body):
        raise StoreError(f"{where}: cannot split the frontmatter from the body exactly")
    return meta, text[:len(text) - len(body)], body


def encode(kind: str, head: str, body: str) -> str:
    return f"{body}{MARKER}{kind}\n{head}{CLOSE}"


def decode(content: str) -> tuple[str, str, str]:
    """→ (kind, head, body); the inverse of `encode`, refusing anything it did not write."""
    at = content.rfind(MARKER)
    if at < 0 or not content.endswith(CLOSE):
        raise StoreError("store node has no hypergraph trailer — it was not written by hypergraph")
    kind, nl, rest = content[at + len(MARKER):].partition("\n")
    if not nl:
        raise StoreError("store node trailer is truncated")
    return kind, rest[:-len(CLOSE)], content[:at]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- the checkout

def main_checkout(start: Path) -> Path:
    """The main working tree for `start` — itself unless `start` is in a git worktree.

    `git rev-parse --git-common-dir` names the shared `.git` of every worktree, so
    its parent is the checkout that holds `.flywheel/` and the graph working copy."""
    try:
        out = subprocess.run(["git", "-C", str(start), "rev-parse", "--path-format=absolute",
                              "--git-common-dir"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return start
    common = Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    if common is None or common.name != ".git":
        return start
    return common.parent


def store_config(config: dict) -> dict | None:
    raw = config.get("store")
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("kind") != STORE_KIND:
        raise StoreError(f"config `store:` must be a mapping with `kind: {STORE_KIND}` "
                         f"(got {raw!r}) — the node files alone need no `store:` block")
    return raw


# ----------------------------------------------------------------- the store

class Store:
    def __init__(self, config: dict, root: Path):
        self.config = config
        self.spec = store_config(config) or {}
        self.root = Path(root)
        self.graph_dir = Path(config.get("graph_dir") or core.DEFAULT_GRAPH_DIR)
        if not self.graph_dir.is_absolute():
            self.graph_dir = self.root / self.graph_dir
        self.state_dir = self.root / ".hypergraph" / "store"
        self.index_path = self.state_dir / "index.json"
        self.kinds = core.graph_kinds(config)
        self.ops = 0
        self._checked_cli = False
        self._tmps: list[str] = []
        self.last_staging: str | None = None
        self._check_cli()   # before anything reads or writes: a format-upgrading CLI must not touch it

    # -- flywheel CLI ---------------------------------------------------------
    def fw(self, *args: str, repo: bool = True) -> dict:
        self._check_cli()
        cmd = ["flywheel", *args, *(["--repo", str(self.root)] if repo else []), "--format=json"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            raise StoreError("the `flywheel` CLI is not on PATH — install it with "
                             "`npm install -g @paradigma-inc/flywheel@<pinned version>`") from None
        if p.returncode:
            raw = (p.stdout or p.stderr).strip()
            try:
                err = json.loads(raw)["error"]
                msg = err.get("message", raw)
                hint = err.get("next_action")
            except (ValueError, KeyError, TypeError):
                msg, hint = raw, None
            raise StoreError(f"flywheel {args[0]}: {msg}" + (f"\n  {hint}" if hint else ""))
        self.ops += 1
        out = json.loads(p.stdout) if p.stdout.strip() else {}
        if isinstance(out, dict) and out.get("staging_digest"):
            self.last_staging = out["staging_digest"]
        return out

    def _check_cli(self) -> None:
        if self._checked_cli:
            return
        self._checked_cli = True
        pin = self.spec.get("flywheel_cli")
        if not pin or os.environ.get("HYPERGRAPH_FLYWHEEL_ANY_VERSION"):
            return
        try:
            got = subprocess.run(["flywheel", "--version"], capture_output=True, text=True,
                                 timeout=60).stdout.strip()
        except FileNotFoundError:
            raise StoreError("the `flywheel` CLI is not on PATH") from None
        if got != str(pin):
            raise StoreError(
                f"flywheel CLI is {got or 'unknown'} but this project pins {pin} "
                "(`store.flywheel_cli`): a newer CLI can upgrade the repository format past "
                "what other machines can read. Install the pinned version, or bump the pin "
                "on every machine together. HYPERGRAPH_FLYWHEEL_ANY_VERSION=1 overrides.")

    def tmp(self, data: str | dict, suffix: str = ".txt") -> str:
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="hg-store-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data) if isinstance(data, dict) else data)
        self._tmps.append(path)
        return path

    def _clean_tmps(self) -> None:
        for path in self._tmps:
            with contextlib.suppress(OSError):
                os.unlink(path)
        self._tmps.clear()

    # -- index and lock -------------------------------------------------------
    def exists(self) -> bool:
        return (self.root / ".flywheel").is_dir()

    def load_index(self) -> dict:
        try:
            return json.loads(self.index_path.read_text())
        except FileNotFoundError:
            return {"version": 1, "head": None, "nodes": {}}

    def save_index(self, index: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
        os.replace(tmp, self.index_path)

    @contextlib.contextmanager
    def lock(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_dir / "lock", "w") as handle:
            deadline = time.monotonic() + LOCK_TIMEOUT_S
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise StoreError(f"the graph store is locked by another writer "
                                         f"for over {LOCK_TIMEOUT_S}s ({self.state_dir / 'lock'})")
                    time.sleep(0.2)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def status(self) -> dict:
        return self.fw("repo:status")

    def head(self) -> str | None:
        return self.status()["heads"]["workspace"]

    # -- the working copy -----------------------------------------------------
    def scan(self) -> dict[str, tuple[str, Path, str]]:
        """→ {slug: (kind, path, text)} for every node file of every configured graph."""
        files: dict[str, tuple[str, Path, str]] = {}
        for kind in self.kinds:
            directory = self.graph_dir / kind
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                if path.stem in files:
                    raise StoreError(f"slug `{path.stem}` is in two graphs "
                                     f"({files[path.stem][0]}, {kind})")
                files[path.stem] = (kind, path, path.read_text())
        return files

    def dirty(self, index: dict, files: dict) -> list[str]:
        nodes = index["nodes"]
        return [s for s, (_, _, text) in files.items()
                if s not in nodes or nodes[s]["sha"] != sha(text)]

    # -- push: working copy → store ----------------------------------------------
    def push(self, message: str, *, batch_ops: int | None = None, progress=None) -> int:
        """Stage and commit every changed node file. → number of nodes committed."""
        index = self.load_index()
        files = self.scan()
        dirty = self.dirty(index, files)
        gone = sorted(set(index["nodes"]) - set(files))
        if gone:
            print(f"warning   {len(gone)} node file(s) the store holds are missing from the "
                  f"working copy ({', '.join(gone[:3])}{'…' if len(gone) > 3 else ''}) — the "
                  "graphs are append-only, so the store keeps them; `hypergraph store pull "
                  "--full` restores the files", file=sys.stderr)
        if not dirty:
            return 0
        self._clear_own_staging(index)
        parsed = {}
        for slug in dirty:
            kind, path, text = files[slug]
            meta, head, body = split_file(text, str(path))
            parsed[slug] = (kind, meta, head, body, text)
        order = self._topo(parsed)
        roots = self._roots(index, files)
        committed, pending_entries, staged_ops = 0, {}, 0
        limit = batch_ops or 10 ** 9
        try:
            for slug in order:
                kind, meta, head, body, text = parsed[slug]
                staged_ops += self._stage_node(index, pending_entries, roots, slug, kind,
                                               meta, head, body, text)
                # what we staged, by digest: an interrupted run's batch is recognisably ours
                index["own_staging"] = self.last_staging
                self.save_index(index)
                if staged_ops >= limit:
                    committed += self._commit(index, pending_entries,
                                              f"{message} (part, through {slug})")
                    staged_ops = 0
                    if progress:
                        progress(committed, len(order))
            committed += self._commit(index, pending_entries, message)
        finally:
            self._clean_tmps()
        return committed

    def _stage_node(self, index, pending, roots, slug, kind, meta, head, body, text) -> int:
        nodes = index["nodes"]
        known = {**nodes, **pending}
        title = str(meta.get("title") or "") or slug
        summary = str(meta.get("summary") or "")
        content = encode(kind, head, body)
        parents = [str(p) for p in (meta.get("parents") or [])]
        entry = known.get(slug)
        ops = 0
        if entry is None:
            made = self.fw("repo:node:create", "--values-file", self.tmp({
                "title": title, "slug_name": slug, "summary": summary or None,
                "content": content, "origin_host": ORIGIN_HOST,
                "external_transcript_ref": None}, ".json"))
            fid = made["node_id"]
            ops += 1
            old_parents: list[str] = []
            root = roots.get(kind)
            if parents and root and root != slug:
                root_id = known.get(root, {}).get("id") or pending.get(root, {}).get("id")
                if root_id is None:
                    raise StoreError(f"the {kind} root `{root}` is not in the store yet")
                self.fw("repo:containment:assign", root_id, fid)
                ops += 1
        else:
            fid = entry["id"]
            old_parents = list(entry.get("parents") or [])
            for field, new, old in (("title", title, entry.get("title")),
                                    ("summary", summary or "null", entry.get("summary") or "null"),
                                    ("content", content, None)):
                if field == "content":
                    if entry.get("content_sha") == sha(content):
                        continue
                elif new == old:
                    continue
                self.fw("repo:node:set", fid, "--field", field, "--value-file", self.tmp(new))
                ops += 1
        lookup = {**nodes, **pending}
        for parent in parents:
            if parent not in old_parents:
                if parent not in lookup:
                    raise StoreError(f"`{slug}`: parent `{parent}` is not in the store")
                self.fw("repo:lineage:add", lookup[parent]["id"], fid)
                ops += 1
        for parent in old_parents:
            if parent not in parents and parent in lookup:
                self.fw("repo:lineage:remove", lookup[parent]["id"], fid)
                ops += 1
        pending[slug] = {"id": fid, "kind": kind, "sha": sha(text), "title": title,
                         "summary": summary, "parents": parents, "content_sha": sha(content)}
        return ops

    def _commit(self, index: dict, pending: dict, message: str) -> int:
        if not pending:
            return 0
        made = self.fw("repo:commit", "--message", message)
        index["nodes"].update(pending)
        index["head"] = made.get("head") or made.get("commit_id")
        index.pop("own_staging", None)
        n = len(pending)
        pending.clear()
        self.save_index(index)
        return n

    def _clear_own_staging(self, index: dict) -> None:
        staging = self.status().get("staging") or {}
        if not staging.get("operation_count"):
            return
        if index.get("own_staging") != staging.get("digest"):
            raise StoreError(
                f"the Flywheel repository at {self.root} has {staging['operation_count']} "
                "staged operation(s) hypergraph did not leave — commit or discard them with "
                "`flywheel repo:commit` / `flywheel repo:staging:discard` first")
        # our own batch from an interrupted run: nothing in it reached the index
        self.fw("repo:staging:discard", "--staging-digest", staging["digest"], "--confirm")

    def _topo(self, parsed: dict) -> list[str]:
        out, done = [], set()

        def visit(slug, trail=()):
            if slug in done or slug not in parsed:
                return
            if slug in trail:
                raise StoreError(f"parent cycle through `{slug}`")
            for parent in parsed[slug][1].get("parents") or []:
                visit(str(parent), trail + (slug,))
            done.add(slug)
            out.append(slug)

        for slug in sorted(parsed, key=lambda s: (str(parsed[s][1].get("created_at")), s)):
            visit(slug)
        return out

    def _roots(self, index: dict, files: dict) -> dict[str, str]:
        roots: dict[str, str] = {}
        for slug, (kind, path, text) in files.items():
            meta, _ = core.split_frontmatter(text, str(path))
            if not meta.get("parents"):
                roots.setdefault(kind, slug)
        return roots

    # -- refresh / pull: store → working copy -------------------------------------
    def refresh(self, *, full: bool = False) -> int:
        """Re-materialize the nodes the store changed since the index. → files written."""
        index = self.load_index()
        head = self.head()
        if not full and head == index.get("head"):
            return 0
        ids = None if full or not index.get("head") else self._changed_ids(index["head"], head)
        if ids is None:
            ids = [n["node_id"] for n in self._list_all()]
        by_id = {e["id"]: s for s, e in index["nodes"].items()}
        files = self.scan()
        got = self._get_many(ids)
        written = 0
        for node in got:
            if node is None or MARKER not in (node.get("content") or ""):
                continue   # not a node hypergraph wrote (a hosted collaborator's own node)
            kind, head_text, body = decode(node["content"])
            text = head_text + body
            meta, _ = core.split_frontmatter(text, f"store node {node['node_id']}")
            slug = str(meta.get("slug") or node.get("slug_name") or "")
            if not core.SLUG_RE.fullmatch(slug):
                raise StoreError(f"store node {node['node_id']} carries no valid slug")
            old = by_id.get(node["node_id"])
            entry = index["nodes"].get(slug)
            local = files.get(slug)
            if local and entry and local[2] != text and sha(local[2]) != entry["sha"]:
                raise StoreError(
                    f"`{slug}` changed both in the working copy and in the store — "
                    f"refusing to overwrite {local[1]}; move the local edit aside and rerun")
            path = self.graph_dir / kind / f"{slug}.md"
            if not local or local[2] != text:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
                written += 1
            content = node["content"]
            index["nodes"][slug] = {
                "id": node["node_id"], "kind": kind, "sha": sha(text),
                "title": node.get("title") or slug, "summary": node.get("summary") or "",
                "parents": [str(p) for p in (meta.get("parents") or [])],
                "content_sha": sha(content)}
            if old and old != slug:
                index["nodes"].pop(old, None)
        index["head"] = head
        self.save_index(index)
        return written

    def _changed_ids(self, base: str, head: str) -> list[str] | None:
        try:
            diff = self.fw("repo:diff", "--base", base, "--head", head)
        except StoreError:
            return None   # base no longer in history (a rebase on pull): rescan everything
        ids = {c["owner_id"] for c in diff.get("latest_field_changes") or []
               if c.get("owner_type") == "node"}
        for op in diff.get("operation_changes") or []:
            for key in ("node_id", "child_node_id"):
                if op.get(key):
                    ids.add(op[key])
        return sorted(ids)

    def _list_all(self) -> list[dict]:
        out, cursor, at = [], None, None
        while True:
            d = self.fw("repo:node:list", *(["--after", cursor, "--at_head", at] if cursor else []))
            out += d["nodes"]
            cursor, at = d.get("next_cursor"), d.get("at_head")
            if not cursor:
                return out

    def _get_many(self, ids: list[str]) -> list[dict | None]:
        def get(nid):
            try:
                return self.fw("repo:node:get", nid)["node"]
            except StoreError:
                return None
        with ThreadPoolExecutor(READ_WORKERS) as pool:
            return list(pool.map(get, ids))

    # -- verify ---------------------------------------------------------------------
    def verify(self) -> list[str]:
        """Rebuild every node from the store and compare bytes with the working copy."""
        problems = []
        files = self.scan()
        seen = set()
        for node in self._get_many([n["node_id"] for n in self._list_all()]):
            if node is None:
                problems.append("a listed store node could not be read")
                continue
            if MARKER not in (node.get("content") or ""):
                continue
            kind, head_text, body = decode(node["content"])
            text = head_text + body
            meta, _ = core.split_frontmatter(text, node["node_id"])
            slug = str(meta.get("slug"))
            seen.add(slug)
            if slug not in files:
                problems.append(f"{slug}: in the store, missing from the working copy")
            elif files[slug][2] != text:
                problems.append(f"{slug}: working copy differs from the store")
            elif files[slug][0] != kind:
                problems.append(f"{slug}: store says {kind}, working copy says {files[slug][0]}")
        for slug in sorted(set(files) - seen):
            problems.append(f"{slug}: in the working copy, not in the store")
        return problems


# --------------------------------------------------------------------- the CLI

READ_ONLY = frozenset({"check", "render", "hwm", "skills", "store"})


def run_with_store(args, config: dict, root: Path, func):
    """Wrap one core command: lock, refresh from the store, run, push what changed."""
    store = Store(config, root)
    if not store.exists():
        raise StoreError(
            f"this project keeps its graphs in a Flywheel repository (`store:` in its "
            f"config) and there is none at {root / '.flywheel'} — on a new machine run "
            "`hypergraph store init` (an empty one) or restore/clone the repository there")
    command = getattr(args, "command", "?")
    with store.lock():
        store.refresh()
        rc = func(args)
        if rc == 0:
            n = store.push(describe(args, command))
            if n:
                print(f"store     {n} node(s) committed to the Flywheel repository", file=sys.stderr)
    return rc


def describe(args, command: str) -> str:
    bits = [f"hypergraph {command}"]
    for attr in ("kind", "slug", "action", "name", "title"):
        value = getattr(args, attr, None)
        if isinstance(value, str) and value:
            bits.append(value if attr != "title" else f"— {value[:120]}")
    return " ".join(bits)


def cmd_store(args, config: dict, root: Path) -> int:
    store = Store(config, root)
    action = args.action
    if action == "init":
        if not store.exists():
            store.fw("repo:init", str(root), repo=False)
            print(f"store     initialized a Flywheel repository at {root / '.flywheel'}")
        with store.lock():
            index = store.load_index()
            if index["nodes"] and not args.force:
                print(f"store     already tracks {len(index['nodes'])} node(s); `store push` "
                      "commits new edits (pass --force to re-run the import)")
                return 0
            start = time.monotonic()
            total = len(store.dirty(index, store.scan()))
            print(f"store     importing {total} node file(s) — about "
                  f"{max(1, round(total * 1.3 / 60))} min", flush=True)

            def progress(done, n):
                print(f"store     {done}/{n} nodes committed "
                      f"({time.monotonic() - start:.0f}s)", flush=True)
            n = store.push(args.message or "hypergraph store init: import the node files",
                           batch_ops=BATCH_OPS, progress=progress)
            print(f"store     imported {n} node(s) in {time.monotonic() - start:.0f}s "
                  f"({store.ops} flywheel calls)")
        return 0
    if not store.exists():
        raise StoreError(f"no Flywheel repository at {root / '.flywheel'} — `hypergraph store init`")
    if action == "status":
        index = store.load_index()
        head = store.head()
        dirty = store.dirty(index, store.scan())
        print(f"store     {STORE_KIND} at {root}")
        print(f"  head        {head}")
        print(f"  index head  {index.get('head')}{'' if head == index.get('head') else '  (behind: run `hypergraph store pull`)'}")
        print(f"  nodes       {len(index['nodes'])} tracked, {len(dirty)} changed in the working copy")
        return 0
    with store.lock():
        if action == "push":
            n = store.push(args.message or "hypergraph store push")
            print(f"store     {n} node(s) committed")
            return 0
        if action == "pull":
            n = store.refresh(full=args.full)
            print(f"store     {n} node file(s) written from the store")
            return 0
        if action == "verify":
            problems = store.verify()
            for p in problems[:50]:
                print(f"VIOLATION {p}")
            print(f"store verify: {len(problems)} difference(s) between the store and the working copy")
            return 1 if problems else 0
    raise StoreError(f"unknown store action {action!r}")
