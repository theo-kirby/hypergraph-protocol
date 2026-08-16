"""`hypergraph heal`: carrying a capability backwards into an already-adopted repo.

The tests that carry the argument are the ones about what heal must **not** do —
never write the archive, never change a body, never need a second run to converge,
never act without `--apply`. A repair that can destroy work is not a repair.
"""
import json
import subprocess
from pathlib import Path

import pytest

from graph_fixtures import (ARCHIVE_TAGS, archive_export_of, create_result,
                            forked_graph, hg, local_graph_copy)
from test_mirror import FakeTransport, RECORD_ROOT, STATE_ROOT


def run(*argv):
    return hg.main([str(a) for a in argv])


def project(tmp_path, *, pushed=False, git=True):
    """A forked (adopted) repo: node files with `origin:`, a config, a cached pull."""
    repo = tmp_path / "repo"
    (repo / ".hypergraph").mkdir(parents=True)
    graph_dir = forked_graph(repo / ".hypergraph")     # → repo/.hypergraph/graph
    export = archive_export_of(graph_dir)
    cache = repo / ".hypergraph" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "mirror-pull.json").write_text(json.dumps(export))

    if pushed:
        # what a completed `push` leaves: a *separate* mirror identity beside origin
        plan = hg.push_plan(graph_dir, do_tags=False)
        hg.apply_push_results(graph_dir, [create_result(op) for op in plan["ops"]])

    config = {
        "project": "adopted", "graph_dir": str(graph_dir), "cache_dir": str(cache),
        "mirror": "flywheel",
        "mirror_roots": {"record": {"node_id": RECORD_ROOT},
                         "state": {"node_id": STATE_ROOT}},
        "archive": {"backend": "flywheel",
                    "roots": [{"node_id": "arch-wise-anchor-1001",
                               "slug": "wise-anchor-1001", "title": "archive root"}]},
    }
    config_path = repo / ".hypergraph" / "config.yml"
    import yaml
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    if git:
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                        "user.name=t", "commit", "-qm", "adopt"], check=True)
    return repo, graph_dir, config_path


def heal(repo, config_path, *argv):
    return run("heal", "tags", "--repo", repo, "--config", config_path, *argv)


def heal_named(repo, config_path, name, *argv):
    """`heal` for one named healer — `heal()` above is hard-wired to `tags`."""
    return run("heal", name, "--repo", repo, "--config", config_path, *argv)


def heal_named_out(capsys, repo, config_path, name, *argv):
    capsys.readouterr()
    code = heal_named(repo, config_path, name, *argv)
    return code, capsys.readouterr().out


def tags_of(graph_dir, slug):
    node = next(iter(p for p in Path(graph_dir).glob(f"*/{slug}.md")))
    meta, _body = hg.split_frontmatter(node.read_text())
    return meta.get("tags")


# ------------------------------------------------------------------- the registry

def test_registry_names_unique_ordering_acyclic_archive_readers_never_write():
    """The cheap invariant that keeps healer number two cheap.

    Every clause here is a thing a second healer could get wrong in a way no other
    test would notice, because a broken healer is only exercised by running it."""
    names = [h.name for h in hg.HEALERS]
    assert names == sorted(set(names), key=names.index), "healer names must be unique"
    assert all(names.count(n) == 1 for n in names)

    for healer in hg.HEALERS:
        assert healer.summary and healer.since and healer.reads
        assert healer.reads in ("archive", "mirror", "local")
        assert healer.writes and all(w in ("frontmatter", "tags", "mirror")
                                     for w in healer.writes)
        # An archive is frozen by definition: a healer may read one, never write one.
        assert "archive" not in healer.writes
        for dependency in healer.after:
            assert dependency in names, f"{healer.name} depends on unknown {dependency}"
            assert names.index(dependency) < names.index(healer.name), \
                f"{healer.name} must run after {dependency}, but is registered first"
        # blocked_by returns a REASON or None — never a bool, so `heal --list` can
        # print *why* rather than just that it does not apply.
        verdict = healer.blocked_by({}, Path("/nonexistent"))
        assert verdict is None or isinstance(verdict, str)


def test_heal_with_no_healer_lists_the_registry_and_exits_zero(tmp_path, capsys):
    repo, _graph_dir, config_path = project(tmp_path)
    assert run("heal", "--repo", repo, "--config", config_path) == 0
    out = capsys.readouterr().out
    assert "tags" in out and "applies" in out


def test_heal_says_why_it_does_not_apply(tmp_path, capsys):
    """A repo that never imported anything has no original tags to recover."""
    from graph_fixtures import local_graph_copy
    graph_dir = local_graph_copy(tmp_path)
    reason = hg.tags_blocked_by({"graph_dir": str(graph_dir)}, tmp_path)
    assert reason and "origin:" in reason


# ------------------------------------------------------------------- the default

def test_heal_is_dry_run_by_default_and_writes_nothing(tmp_path, capsys):
    repo, graph_dir, config_path = project(tmp_path)
    before = {p: p.read_bytes() for p in Path(graph_dir).rglob("*.md")}
    assert heal(repo, config_path, "--offline") == 0
    assert {p: p.read_bytes() for p in Path(graph_dir).rglob("*.md")} == before
    assert not (repo / ".hypergraph" / "tags.yml").exists()
    out = capsys.readouterr().out
    assert "would heal" in out and "dry run" in out


def test_plain_detected_drift_is_exit_zero_and_fail_on_drift_is_opt_in(tmp_path):
    """Unhealed drift is a capability that landed after your adoption, not a broken
    invariant — the same reasoning `check_version_skew` uses to stay a warning."""
    repo, _graph_dir, config_path = project(tmp_path)
    assert heal(repo, config_path, "--offline") == 0
    assert heal(repo, config_path, "--offline", "--fail-on-drift") == 1


# --------------------------------------------------------------- the local phase

def test_heal_tags_recovers_the_archive_names_and_the_vocabulary(tmp_path):
    repo, graph_dir, config_path = project(tmp_path)
    assert heal(repo, config_path, "--offline", "--apply") == 0
    assert tags_of(graph_dir, "brave-otter-1002") == ["kind:experiment", "outcome:GREEN"]
    assert tags_of(graph_dir, "wise-anchor-1001") is None       # untagged on the archive

    vocab = hg.load_tag_vocab(repo / ".hypergraph" / "tags.yml")
    names = hg.declared_tag_names(vocab)
    assert "kind:experiment" in names and "outcome:GREEN" in names
    # the pointer tag travels transliterated, with the original kept
    assert "studio-baseline" in names
    entry = next(e for e in hg.tag_vocab_entries(vocab) if e["name"] == "studio-baseline")
    assert entry["archive_name"] == "★ studio-baseline"
    assert entry["one_only"] is True and entry["bg_color"] == "#7A5A1A"


def test_heal_resolves_tag_ids_through_the_union_not_one_nodes_copy(tmp_path):
    """The 130/59 split. Only some archive nodes echo `graph_tags`; a resolver that
    reads a single node's copy loses every tag on the rest [rec: fresh-spire-9002]."""
    repo, graph_dir, config_path = project(tmp_path)
    export = json.loads((repo / ".hypergraph" / "cache" / "mirror-pull.json").read_text())
    silent = [n for n in export["nodes"] if not n["graph_tags"] and n["tag_ids"]]
    assert silent, "the fixture must contain nodes that carry tag_ids and no vocabulary"
    assert heal(repo, config_path, "--offline", "--apply") == 0
    for node in silent:
        assert tags_of(graph_dir, node["slug_name"]), \
            f"{node['slug_name']} echoed no vocabulary and lost its tags"


def test_heal_names_match_what_import_would_have_written(tmp_path):
    """Heal and import must agree, or `★ studio-baseline` and `studio-baseline`
    become two tags meaning one thing — the duplicate failure by another route."""
    repo, graph_dir, config_path = project(tmp_path)
    export_path = repo / ".hypergraph" / "cache" / "mirror-pull.json"
    assert heal(repo, config_path, "--offline", "--apply") == 0
    healed = {p.stem: tags_of(graph_dir, p.stem) for p in Path(graph_dir).rglob("*.md")}

    fresh = tmp_path / "fresh"
    assert run("import", "--record", export_path, "--fork", "--graph-dir", fresh) == 0
    imported = {}
    for kind in ("record", "state"):
        for slug, node in hg.load_local_nodes(fresh, kind, missing_ok=True).items():
            imported[slug] = node.tags or None
    assert healed == imported


def test_heal_never_overwrites_an_authored_tag_set(tmp_path, capsys):
    repo, graph_dir, config_path = project(tmp_path)
    path = next(Path(graph_dir).glob("*/brave-otter-1002.md"))
    meta, body = hg.split_frontmatter(path.read_text())
    meta["tags"] = ["cluster:mine"]
    path.write_text(hg.render_node_file(meta, body))
    assert heal(repo, config_path, "--offline", "--apply", "--allow-dirty") == 0
    assert tags_of(graph_dir, "brave-otter-1002") == ["cluster:mine"]
    assert "never overwrites an authored tag set" in capsys.readouterr().out


def test_heal_tags_is_idempotent(tmp_path):
    repo, graph_dir, config_path = project(tmp_path)
    assert heal(repo, config_path, "--offline", "--apply") == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "healed"], check=True)
    assert heal(repo, config_path, "--offline", "--apply") == 0
    assert subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                          capture_output=True, text=True).stdout.strip() == ""


def test_heal_tags_changes_no_body_sha256_and_leaves_push_plan_empty(tmp_path):
    """The append-only proof.

    `LocalNode.sha256` hashes the body alone, so a frontmatter-only write must produce
    no `update` op — otherwise a heal on a *record* node would trip the append-only
    violation in `push_plan` and be unrunnable on the graph it exists for."""
    repo, graph_dir, config_path = project(tmp_path, pushed=True)
    before = {slug: node.sha256
              for kind in ("record", "state")
              for slug, node in hg.load_local_nodes(graph_dir, kind).items()}
    assert heal(repo, config_path, "--offline", "--apply") == 0
    after = {slug: node.sha256
             for kind in ("record", "state")
             for slug, node in hg.load_local_nodes(graph_dir, kind).items()}
    assert after == before

    plan = hg.push_plan(graph_dir, do_tags=False)
    assert plan["ops"] == [] and plan["violations"] == []
    # with tags on, the only ops are the assignments — no creates, no body updates
    creates, updates, tags, artifacts = hg.plan_op_counts(hg.push_plan(graph_dir))
    assert (creates, updates, artifacts) == (0, 0, 0) and tags == 4


def test_limit_is_never_a_silent_cap(tmp_path, capsys):
    repo, _graph_dir, config_path = project(tmp_path)
    assert heal(repo, config_path, "--offline", "--limit", "1") == 0
    assert "the rest are NOT addressed" in capsys.readouterr().err


# ------------------------------------------------------------------- the refusals

def test_heal_never_writes_the_archive(tmp_path):
    """`origin.*` is never a write target.

    In an adopted repo every `origin.node_id` is an id on the frozen archive, one
    attribute lookup away from the mirror id in the same dict and reachable with the
    same credentials. This is the guardrail hypergraph-adopt has only stated in prose."""
    repo, graph_dir, config_path = project(tmp_path, pushed=True)
    config = hg.load_config(config_path)

    targets = hg.heal_write_targets(graph_dir, config)
    assert targets and all(v.startswith("fw-") for v in targets.values())
    origins = {str((node.meta.get("origin") or {}).get("node_id"))
               for kind in ("record", "state")
               for node in hg.load_local_nodes(graph_dir, kind).values()}
    assert not (set(targets.values()) & origins)

    # confusing the two is refused, not silently obeyed
    path = next(Path(graph_dir).glob("*/brave-otter-1002.md"))
    meta, body = hg.split_frontmatter(path.read_text())
    meta["flywheel"]["node_id"] = meta["origin"]["node_id"]
    path.write_text(hg.render_node_file(meta, body))
    with pytest.raises(hg.LocalGraphError, match="frozen archive"):
        hg.heal_write_targets(graph_dir, config)

    # and so is naming a declared archive root as a push target
    meta["flywheel"]["node_id"] = "arch-wise-anchor-1001"
    meta["origin"]["node_id"] = "something-else"
    path.write_text(hg.render_node_file(meta, body))
    with pytest.raises(hg.LocalGraphError, match="archive:"):
        hg.heal_write_targets(graph_dir, config)


def test_heal_refuses_an_uncommitted_graph_dir(tmp_path):
    repo, graph_dir, config_path = project(tmp_path)
    path = next(Path(graph_dir).glob("*/brave-otter-1002.md"))
    path.write_text(path.read_text() + "\nan uncommitted edit\n")
    assert heal(repo, config_path, "--offline", "--apply") == 2   # LocalGraphError → 2
    # detection is read-only, so a dirty tree does not block it
    assert hg.heal_dirty_block(graph_dir, repo) is not None


def test_heal_refuses_the_protocols_own_checkout(tmp_path, capsys):
    root = hg.skills_data_root()
    assert run("heal", "tags", "--repo", root) == 2
    assert "protocol's own checkout" in capsys.readouterr().err


# ------------------------------------------------------------------ the mirror phase

def mirror_project(tmp_path, monkeypatch):
    repo, graph_dir, config_path = project(tmp_path, pushed=True)
    fake = FakeTransport(graph_dir)
    monkeypatch.setattr(hg, "make_transport", lambda *a, **kw: fake)
    monkeypatch.setattr(hg, "publish_branch_block", lambda *a, **kw: None)
    real_pacer = hg.Pacer
    monkeypatch.setattr(hg, "Pacer", lambda *_a, **_kw: real_pacer(
        0.0, sleep=lambda _s: None, clock=lambda: 0.0))
    # the mirror already holds the pushed nodes, hung under the mirror roots so a
    # verify export reaches them
    for kind, root in (("record", RECORD_ROOT), ("state", STATE_ROOT)):
        for slug, node in hg.load_local_nodes(graph_dir, kind).items():
            parents = [f"fw-{p}" for p in node.parents] or [root]
            fake.nodes[f"fw-{slug}"] = {
                "node_id": f"fw-{slug}", "slug_name": f"wild-river-{slug[-4:]}",
                "title": node.title, "content": node.content,
                "summary": str(node.meta.get("summary") or ""), "revision": 1,
                "can_write": True, "is_owner": True, "parent_ids": parents}
            for parent in parents:
                fake.kids.setdefault(parent, []).append(f"fw-{slug}")
            fake.kids.setdefault(f"fw-{slug}", [])
    return repo, graph_dir, config_path, fake


def test_heal_tags_publishes_the_vocabulary_and_assignments(tmp_path, monkeypatch):
    repo, graph_dir, config_path, fake = mirror_project(tmp_path, monkeypatch)
    assert heal(repo, config_path, "--offline", "--apply") == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "local heal"], check=True)
    assert heal(repo, config_path, "--apply") == 0

    assert sorted(t["name"] for t in fake.tags[RECORD_ROOT]) == \
        ["kind:experiment", "outcome:GREEN", "studio-baseline"]
    assert sorted(fake.nodes["fw-brave-otter-1002"]["tag_ids"]) == \
        ["tag-kind:experiment", "tag-outcome:GREEN"]
    # the archive was never written to
    assert not [c for c in fake.calls if str(c[1]).startswith("arch-")]


def test_heal_tags_folds_the_bumped_revision_so_verify_stays_clean(tmp_path, monkeypatch):
    """`tags:assign` bumps the node revision and `verify_mirror` calls revision skew a
    violation. Skipping the fold is one permanent false drift finding per tagged node —
    188 of them in the field, discovered a week later."""
    repo, graph_dir, config_path, fake = mirror_project(tmp_path, monkeypatch)
    assert heal(repo, config_path, "--offline", "--apply") == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "local heal"], check=True)
    assert heal(repo, config_path, "--apply") == 0

    config = hg.load_config(config_path)
    for kind in ("record", "state"):
        for slug, node in hg.load_local_nodes(graph_dir, kind).items():
            if node.tags:
                assert node.meta["flywheel"]["revision"] == \
                    fake.nodes[f"fw-{slug}"]["revision"]
    report = hg.verify_against_mirror(graph_dir, config, fake,
                                      cache_dir=Path(config["cache_dir"]),
                                      out=lambda *_a: None)
    assert [str(f) for f in report.violations()] == []


def test_heal_tags_resolves_an_existing_tag_by_name_instead_of_creating_a_second(
        tmp_path, monkeypatch):
    """A duplicate tag definition is unrecoverable — `tags:delete` un-tags every node
    that used it. FakeTransport raises on a duplicate, so this test fails loudly."""
    repo, graph_dir, config_path, fake = mirror_project(tmp_path, monkeypatch)
    fake.tags[RECORD_ROOT] = [{"tag_id": "tag-preexisting", "name": "kind:experiment",
                               "bg_color": "#000000", "text_color": "#FFFFFF",
                               "one_only": False, "track_history": False}]
    assert heal(repo, config_path, "--offline", "--apply") == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "local heal"], check=True)
    assert heal(repo, config_path, "--apply") == 0

    assert [t["name"] for t in fake.tags[RECORD_ROOT]].count("kind:experiment") == 1
    # the pre-existing id is *reused*, not shadowed by a second definition
    assert "tag-preexisting" in fake.nodes["fw-brave-otter-1002"]["tag_ids"]
    record_creates = [t["tag_id"] for t in fake.tags[RECORD_ROOT]]
    assert record_creates == ["tag-preexisting", "tag-outcome:GREEN",
                              "tag-studio-baseline"]


def test_a_create_never_reuses_a_stale_root_revision(tmp_path, monkeypatch):
    """Each `tags:create` bumps the root revision. FakeTransport enforces the lock, so
    a loop that computed `+1` instead of re-reading would 409 on the second tag."""
    repo, graph_dir, config_path, fake = mirror_project(tmp_path, monkeypatch)
    before = fake.nodes[RECORD_ROOT]["revision"]
    assert heal(repo, config_path, "--offline", "--apply") == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "local heal"], check=True)
    assert heal(repo, config_path, "--apply") == 0
    assert fake.nodes[RECORD_ROOT]["revision"] == before + 3     # one per tag created


def test_heal_json_reports_findings_and_changes(tmp_path, capsys):
    repo, _graph_dir, config_path = project(tmp_path)
    assert heal(repo, config_path, "--offline", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    entry = payload["healers"][0]
    assert entry["name"] == "tags" and entry["drift"] == 4
    assert len(entry["findings"]) == 4


# --------------------------------------------------------- healer 2: artifacts
# The interesting property is what this healer does *not* do. An adoption that
# predated tags lost the names; an adoption that predated artifacts lost nothing,
# because there was nothing local to lose. So this records an inventory of what the
# frozen archive still holds — and never repatriates the bytes, which are not in the
# repo and would leave the mirror holding evidence the repo cannot regenerate.

def archive_with_attachments(graph_dir, slug="brave-otter-1002"):
    export = archive_export_of(graph_dir)
    for raw in export["nodes"]:
        if raw["slug_name"] == slug:
            raw["artifacts"] = [
                {"artifact_id": "art-9001", "title": "train.log",
                 "artifact_type": "text", "media_type": "text/plain",
                 "created_at": "2026-01-01T00:00:00+00:00"},
                {"artifact_id": "art-9002", "title": "loss.png",
                 "artifact_type": "image"},
            ]
    return export


def test_heal_artifacts_records_the_archive_inventory_under_origin(tmp_path, capsys):
    repo, graph_dir, config_path = project(tmp_path)
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(archive_with_attachments(graph_dir)))
    assert heal_named(repo, config_path, "artifacts", "--offline", "--apply",
                      "--source", source) == 0
    origin = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"].meta["origin"]
    assert [a["artifact_id"] for a in origin["artifacts"]] == ["art-9001", "art-9002"]
    assert origin["artifacts"][0]["title"] == "train.log"
    # untouched nodes stay untouched
    assert "artifacts" not in \
        hg.load_local_nodes(graph_dir, "record")["calm-fern-1003"].meta["origin"]
    capsys.readouterr()


def test_heal_artifacts_never_publishes_the_archives_bytes(tmp_path, capsys):
    repo, graph_dir, config_path = project(tmp_path)
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(archive_with_attachments(graph_dir)))
    code, out = heal_named_out(capsys, repo, config_path, "artifacts", "--offline",
                               "--apply", "--source", source)
    assert code == 0
    assert "publishing them would make the mirror the only holder" in out
    # the local `artifacts:` list — the one `push` uploads — is never written
    node = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    assert node.artifacts == []
    assert [o for o in hg.push_plan(graph_dir, repo=repo)["ops"]
            if o["op"] == "artifacts"] == []


def test_heal_artifacts_changes_no_body_sha256_and_is_idempotent(tmp_path, capsys):
    repo, graph_dir, config_path = project(tmp_path)
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(archive_with_attachments(graph_dir)))
    before = {slug: node.sha256
              for kind in ("record", "state")
              for slug, node in hg.load_local_nodes(graph_dir, kind).items()}
    assert heal_named(repo, config_path, "artifacts", "--offline", "--apply",
                      "--source", source) == 0
    after = {slug: node.sha256
             for kind in ("record", "state")
             for slug, node in hg.load_local_nodes(graph_dir, kind).items()}
    assert after == before
    files = {p: p.read_text() for p in (graph_dir / "record").glob("*.md")}
    assert heal_named(repo, config_path, "artifacts", "--offline", "--apply",
                      "--allow-dirty", "--source", source) == 0
    assert {p: p.read_text() for p in (graph_dir / "record").glob("*.md")} == files
    capsys.readouterr()


def test_heal_artifacts_does_not_apply_without_an_import(tmp_path, capsys):
    """The normal case needs no healer, and the message has to say why."""
    graph_dir = local_graph_copy(tmp_path)
    reason = hg.artifacts_blocked_by({"graph_dir": str(graph_dir)}, tmp_path)
    assert "artifacts add" in reason and "nothing to heal" in reason


# --------------------------------------------------------------- the upgrade fold
# At 0.9.0 `heal` folded into `upgrade --graph`: one verb, two polarities. The
# copies half writes by default (git-checkout-reversible); everything behind
# `--graph` is detect-only until `--apply`. `heal` survives as a hidden alias for
# the 0.9.x series.

def upgrade_graph(repo, config_path, *argv):
    return run("upgrade", "--repo", repo, "--config", config_path, "--graph", *argv)


def test_upgrade_graph_bare_lists_the_registry_exactly_like_bare_heal(
        tmp_path, capsys):
    repo, _graph_dir, config_path = project(tmp_path)
    assert upgrade_graph(repo, config_path) == 0
    via_upgrade = capsys.readouterr().out
    assert run("heal", "--repo", repo, "--config", config_path) == 0
    via_alias = capsys.readouterr().out
    assert via_upgrade == via_alias
    assert "tags" in via_upgrade and "applies" in via_upgrade


def test_upgrade_graph_detects_the_same_drift_as_heal(tmp_path, capsys):
    repo, _graph_dir, config_path = project(tmp_path)
    assert upgrade_graph(repo, config_path, "tags", "--offline") == 0
    via_upgrade = capsys.readouterr().out
    assert heal(repo, config_path, "--offline") == 0
    via_alias = capsys.readouterr().out
    assert via_upgrade == via_alias
    assert "would change" in via_upgrade


def test_upgrade_graph_is_detect_only_until_apply(tmp_path, capsys):
    repo, graph_dir, config_path = project(tmp_path)
    before = {p: p.read_bytes() for p in Path(graph_dir).rglob("*.md")}
    assert upgrade_graph(repo, config_path, "tags", "--offline") == 0
    assert {p: p.read_bytes() for p in Path(graph_dir).rglob("*.md")} == before
    assert not (repo / ".hypergraph" / "tags.yml").exists()
    assert upgrade_graph(repo, config_path, "tags", "--offline", "--apply") == 0
    assert tags_of(graph_dir, "brave-otter-1002") == ["kind:experiment",
                                                      "outcome:GREEN"]
    capsys.readouterr()


def test_heal_alias_still_works_and_names_its_replacement(tmp_path, capsys):
    repo, _graph_dir, config_path = project(tmp_path)
    assert run("heal", "--repo", repo, "--config", config_path) == 0
    err = capsys.readouterr().err
    assert "deprecated" in err and "upgrade --graph" in err
    # the real verb carries no such note
    assert upgrade_graph(repo, config_path) == 0
    assert "deprecated" not in capsys.readouterr().err


def test_upgrade_graph_refuses_dry_run(tmp_path):
    """--dry-run is the copies half; --graph is already detect-only."""
    repo, _graph_dir, config_path = project(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        upgrade_graph(repo, config_path, "tags", "--dry-run")
    assert excinfo.value.code == 2


def test_help_no_longer_lists_a_heal_command(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run("--help")
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    table = help_text.split("positional arguments:", 1)[1]
    assert not any(line.split()[:1] == ["heal"] for line in table.splitlines())
