"""The two-file split: core offline, mirror networked, one lazy seam between them.

The headline property is the first test — offline commands never *import* the
mirror module, which upgrades the old "no offline command resolves a transport"
guarantee from behavioral to structural. The rest holds the seam itself: one
module object, shared class identities, and packaging that actually ships both
files under the names `_mirror()` looks for.
"""
import subprocess
import sys
from pathlib import Path

from graph_fixtures import LOCAL, hg, hgm, local_graph_copy

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "hypergraph.py"


def run_tool_expecting_no_mirror_import(tmp_path, *argv):
    """Run the CLI in a subprocess and report whether the mirror module loaded.

    A subprocess, not main(): the fixture process imported the mirror module for
    its own re-exports, so an in-process assertion could never fail."""
    probe = (
        "import runpy, sys\n"
        f"sys.argv = [{str(TOOL)!r}] + {[str(a) for a in argv]!r}\n"
        f"try:\n"
        f"    runpy.run_path({str(TOOL)!r}, run_name='__main__')\n"
        "except SystemExit as exc:\n"
        "    code = exc.code or 0\n"
        "loaded = 'hypergraph_mirror' in sys.modules\n"
        "print(f'code={code} mirror_loaded={loaded}')\n"
    )
    proc = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                          text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    tail = proc.stdout.strip().splitlines()[-1]
    assert tail.startswith("code="), proc.stdout
    code, loaded = tail.split()
    return int(code.split("=")[1]), loaded == "mirror_loaded=True"


def test_offline_commands_never_import_the_mirror_module(tmp_path):
    graph_dir = local_graph_copy(tmp_path)
    cache = tmp_path / "cache"

    code, loaded = run_tool_expecting_no_mirror_import(
        tmp_path, "export", "--graph-dir", graph_dir, "--out-dir", cache)
    assert code == 0 and not loaded

    code, loaded = run_tool_expecting_no_mirror_import(
        tmp_path, "check", "--record", cache / "record.json",
        "--state", cache / "state.json")
    assert code == 0 and not loaded

    code, loaded = run_tool_expecting_no_mirror_import(
        tmp_path, "push", "--plan", "--graph-dir", graph_dir,
        "-o", tmp_path / "plan.json")
    assert code == 0 and not loaded

    # a mirror-less push stands down before the module boundary too
    config = tmp_path / "config.yml"
    config.write_text(f"project: t\ngraph_dir: {graph_dir}\n")
    code, loaded = run_tool_expecting_no_mirror_import(
        tmp_path, "push", "--config", config, "--graph-dir", graph_dir)
    assert code == 0 and not loaded


def test_mirror_loader_shares_core_identity():
    """`_mirror()` returns one module object, and its error classes are core's.

    The class-identity half is the reason the loader exists at all: a second copy
    of core would make `except LocalGraphError` in main() miss every MirrorError."""
    assert hg._mirror() is hgm
    assert hg._mirror() is hg._mirror()
    try:
        raise hgm.MirrorAuthError("boom")
    except hg.LocalGraphError as exc:
        assert isinstance(exc, hgm.MirrorError)


def test_wheel_and_sdist_ship_the_mirror_module():
    """`_mirror()` looks for hypergraph_protocol_mirror.py beside the installed
    module — the force-include mapping is what puts it there."""
    import tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    targets = cfg["tool"]["hatch"]["build"]["targets"]
    wheel = targets["wheel"]["force-include"]
    assert wheel["tools/hypergraph_mirror.py"] == "hypergraph_protocol_mirror.py"
    assert "tools/hypergraph_mirror.py" in targets["sdist"]["include"]


def test_mirror_module_is_not_a_script():
    """No PEP 723 header and no entry point: the mirror half loads through core
    or not at all. A second `uv run`-able script would be a second CLI to drift."""
    text = (ROOT / "tools" / "hypergraph_mirror.py").read_text()
    assert "/// script" not in text
    assert "env -S uv run" not in text
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "hypergraph_mirror.py")],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert "not a command" in proc.stderr
