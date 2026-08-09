"""The distribution is an allow-list — assert `research/` can never sneak into it.

`research/` holds the benchmark lab: Box drivers, comparison harnesses, captured
run data, chart code. An end user installing the CLI has no use for any of it, so
it must stay out of the wheel and the sdist. Both hatchling targets are allow-lists
today (`force-include` for the wheel, `include` for the sdist), which makes the
exclusion automatic — this test exists so that a future edit adding a broad glob,
or dropping the sdist's explicit `include`, fails here instead of on PyPI.
"""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories that exist in the repo but must never be distributed.
NEVER_SHIP = ("research", "tests", ".hypergraph")


def _pyproject():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_wheel_force_include_is_an_explicit_allow_list():
    """The wheel ships only what force-include names — and never research/."""
    cfg = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]
    # An allow-list is the whole safety property: if `force-include` were ever
    # replaced by a `packages`/`include` glob over the repo root, this fails.
    assert "force-include" in cfg, "wheel target must stay an explicit allow-list"
    for src in cfg["force-include"]:
        top = Path(src).parts[0]
        assert top not in NEVER_SHIP, f"wheel would ship {src}"


def test_sdist_include_is_an_explicit_allow_list():
    """The sdist ships only what `include` names — and never research/."""
    cfg = _pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert "include" in cfg, "sdist target must stay an explicit allow-list"
    for src in cfg["include"]:
        top = Path(src).parts[0]
        assert top not in NEVER_SHIP, f"sdist would ship {src}"


def test_research_tree_exists_and_is_undeclared():
    """Guard the guard: if research/ vanished, the assertions above go vacuous."""
    assert (ROOT / "research").is_dir()
    raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # A path reference, not the bare word — the project description legitimately
    # contains "research projects".
    assert "research/" not in raw, "pyproject must not reference the research/ tree"


def test_module_version_matches_pyproject():
    """`hypergraph --version` must not disagree with the distribution.

    The benchmark's arm-C boxes install `hypergraph-protocol==<pyproject version>`
    and then assert the version the CLI reports, because `uv tool install` reuses
    a cached tool and would otherwise leave a box silently running an older build
    while the write-up names this one. That assertion is only meaningful if the
    two numbers are the same number here.
    """
    import re
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    source = (ROOT / "tools" / "hypergraph.py").read_text(encoding="utf-8")
    in_module = re.search(r'^__version__ = "([^"]+)"', source, re.M)
    assert in_module, "tools/hypergraph.py declares no __version__"
    assert in_module.group(1) == declared, (
        f"tools/hypergraph.py says {in_module.group(1)}, pyproject says {declared}")


def test_spec_header_matches_pyproject():
    """SPEC.md's version header must not drift from the distribution.

    It did: the spec said v0.0.2 while the tool shipped 0.0.3, so the document
    describing the protocol disagreed with the artifact implementing it. Four lines
    closes that permanently — SPEC.md is the durable publication artifact, and a
    wrong version number on it is a claim about which protocol you are reading.
    """
    import re
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    header = (ROOT / "SPEC.md").read_text(encoding="utf-8").splitlines()[0]
    found = re.search(r"v(\d+\.\d+\.\d+)", header)
    assert found, f"SPEC.md's first line carries no version: {header!r}"
    assert found.group(1) == declared, (
        f"SPEC.md says v{found.group(1)}, pyproject says {declared}")


def test_sdist_actually_contains_the_skills_tree(tmp_path):
    """Build the sdist and look inside it. The static assertions above cannot see this.

    `.claude/skills/hypergraph-*` are committed symlinks into `skills/`, and hatchling
    walks with `followlinks=True` while skipping any directory whose `(st_dev, st_ino)`
    it has already seen. So it materialized the skills under `.claude/` and then dropped
    the real `skills/` as a duplicate — an sdist with no `skills/` at all, whose wheel
    build fails on the force-include of it. Every declaration in pyproject was correct;
    only the built artifact was wrong, which is why this test builds one.

    `exclude` alone does not fix it: it filters the output, not the walk. The fix is
    `skip-excluded-dirs = true`, and this test is what keeps it there.
    """
    import shutil
    import subprocess
    import tarfile

    if shutil.which("uv") is None:
        import pytest
        pytest.skip("uv is not on PATH")

    proc = subprocess.run(["uv", "build", "--sdist", "--out-dir", str(tmp_path)],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"sdist build failed:\n{proc.stderr}"

    sdists = list(tmp_path.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected one sdist, got {sdists}"
    with tarfile.open(sdists[0]) as tar:
        names = ["/".join(n.split("/")[1:]) for n in tar.getnames()]

    for src in _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]:
        assert any(n == src or n.startswith(src.rstrip("/") + "/") for n in names), (
            f"the wheel force-includes {src!r}, but the sdist does not carry it — "
            "building a wheel from this sdist would fail")

    for never in NEVER_SHIP:
        assert not any(n.split("/")[0] == never for n in names), f"sdist ships {never}/"
    assert not any(n.split("/")[0] == ".claude" for n in names), (
        "sdist ships the .claude symlink tree, which shadows skills/ during the walk")
