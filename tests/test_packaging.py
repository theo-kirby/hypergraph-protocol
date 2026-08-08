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
