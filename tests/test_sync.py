"""End-to-end tests for `sync` (export → render → check → push) and the `hwm` CLI.

`sync` is the one verb the skills tell every agent to run, and until now nothing
executed it in the suite: the offline path, the violation gate, the publishing path
and the hand-built push Namespace were all held by prose. The parity pin at the
bottom is the loud failure for the quiet bug class: a new `push` flag that `sync`
forgets to forward.
"""
import argparse
import json
from pathlib import Path

import yaml

from graph_fixtures import (CLEAN, FakeTransport, config_for, hg, hgm,
                            local_graph_copy)


def run(*argv):
    return hg.main([str(a) for a in argv])


def write_config(tmp_path, cfg):
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path


def offline_config(tmp_path, graph_dir, **extra):
    cfg = {"project": "t", "graph_dir": str(graph_dir),
           "cache_dir": str(tmp_path / "cache"),
           "state_md": str(tmp_path / "STATE.md"),
           "record_root": {"slug": "wise-anchor-1001"},
           "state_root": {"slug": "bright-harbor-2001"}}
    cfg.update(extra)
    return write_config(tmp_path, cfg)


def test_sync_offline_writes_exports_and_state_md_without_the_mirror(
        tmp_path, monkeypatch, capsys):
    """No mirror configured: sync exports, renders, checks, and stands down at the
    push gate without ever touching the mirror module."""
    monkeypatch.setattr(hg, "_mirror", lambda: (_ for _ in ()).throw(
        AssertionError("sync imported the mirror module with no mirror configured")))
    graph_dir = local_graph_copy(tmp_path)
    cfg = offline_config(tmp_path, graph_dir)
    assert run("sync", "--config", cfg) == 0
    out = capsys.readouterr().out
    assert "no mirror configured" in out
    for kind in ("record", "state"):
        exported = json.loads((tmp_path / "cache" / f"{kind}.json").read_text())
        assert exported["nodes"]
    assert "## Frontier" in (tmp_path / "STATE.md").read_text()


def test_sync_with_a_violation_exits_1_and_never_builds_a_transport(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hgm, "make_transport", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("a violating sync built a transport")))
    graph_dir = local_graph_copy(tmp_path)
    node = graph_dir / "state" / "quiet-summit-2002.md"
    node.write_text(node.read_text().replace("Status: working", "Status: done"))
    cfg = offline_config(tmp_path, graph_dir,
                         **{"mirror": "flywheel",
                            "mirror_roots": {"record": {"node_id": "host-root-record"},
                                             "state": {"node_id": "host-root-state"}}})
    assert run("sync", "--config", cfg) == 1
    captured = capsys.readouterr()
    assert "not publishing" in captured.err
    assert "VIOLATION I6" in captured.out


def test_sync_no_push_stops_after_a_clean_check(tmp_path, monkeypatch):
    monkeypatch.setattr(hg, "cmd_push", lambda ns: (_ for _ in ()).throw(
        AssertionError("--no-push reached the push step")))
    graph_dir = local_graph_copy(tmp_path)
    cfg = offline_config(tmp_path, graph_dir)
    assert run("sync", "--no-push", "--config", cfg) == 0
    assert (tmp_path / "STATE.md").exists()


def test_sync_with_a_mirror_publishes_and_stamps_the_node_files(
        tmp_path, monkeypatch):
    graph_dir = local_graph_copy(tmp_path)
    fake = FakeTransport(graph_dir)
    monkeypatch.setattr(hgm, "make_transport", lambda *a, **kw: fake)
    monkeypatch.setattr(hg, "publish_branch_block", lambda *a, **kw: None)
    monkeypatch.setattr(hgm, "mirror_doctor", lambda *a, **kw: hg.Report())
    cfg_dict = config_for(graph_dir,
                          cache_dir=str(tmp_path / "cache"),
                          state_md=str(tmp_path / "STATE.md"),
                          record_root={"slug": "wise-anchor-1001"},
                          state_root={"slug": "bright-harbor-2001"})
    assert run("sync", "--config", write_config(tmp_path, cfg_dict)) == 0
    expected = {"fw-wise-anchor-1001", "fw-brave-otter-1002", "fw-calm-fern-1003",
                "fw-bright-harbor-2001", "fw-quiet-summit-2002"}
    assert expected <= set(fake.landed())   # 3 record + 2 state (+ the slug legend)
    for kind in ("record", "state"):
        for node in hg.load_local_nodes(graph_dir, kind).values():
            assert node.meta.get("flywheel", {}).get("node_id"), \
                f"{node.slug} was not stamped with its mirror identity"


def test_sync_namespace_covers_every_push_option(tmp_path, monkeypatch):
    """The parity pin: cmd_sync hand-builds the push Namespace, so a new `push`
    subparser option that sync does not forward must fail here, loudly."""
    captured = {}
    monkeypatch.setattr(hg, "cmd_push", lambda ns: (captured.update(vars(ns)), 0)[1])
    graph_dir = local_graph_copy(tmp_path)
    cfg = offline_config(tmp_path, graph_dir)
    assert run("sync", "--config", cfg) == 0

    sub = next(a for a in hg.build_parser()._actions
               if isinstance(a, argparse._SubParsersAction))
    push_dests = {a.dest for a in sub.choices["push"]._actions} - {"help"}
    missing = push_dests - set(captured)
    assert not missing, f"cmd_sync's hand-built push Namespace misses {sorted(missing)}"


# ------------------------------------------------------------------- hwm CLI

def test_hwm_reports_the_frontier_and_the_unreconciled_count(capsys):
    assert run("hwm", "--record", CLEAN / "record.json",
               "--state", CLEAN / "state.json") == 0
    out = capsys.readouterr().out
    assert "high_water_mark: dim-walrus-0004" in out
    assert "0 unreconciled record node(s)" in out


def test_hwm_with_an_unresolvable_mark_exits_1(tmp_path, capsys):
    graph = json.loads((CLEAN / "state.json").read_text())
    for node in graph["nodes"]:
        node["content"] = node["content"].replace(
            "high_water_mark: dim-walrus-0004", "high_water_mark: ghost-walrus-9999")
    path = tmp_path / "state.json"
    path.write_text(json.dumps(graph))
    assert run("hwm", "--record", CLEAN / "record.json", "--state", path) == 1
    assert "does not resolve" in capsys.readouterr().out


def test_hwm_suggest_prints_an_adoptable_frontier_line(capsys):
    assert run("hwm", "--suggest", "--record", CLEAN / "record.json",
               "--state", CLEAN / "state.json") == 0
    assert "high_water_mark: " in capsys.readouterr().out


def test_hwm_tips_prints_the_record_graphs_childless_tips(capsys):
    assert run("hwm", "--tips", "--record", CLEAN / "record.json",
               "--state", CLEAN / "state.json") == 0
    out = capsys.readouterr().out
    assert out.strip() == "high_water_mark: dim-walrus-0004"
