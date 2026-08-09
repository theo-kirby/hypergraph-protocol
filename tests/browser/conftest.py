"""Playwright harness for the viz page — dev group only, skips when unavailable.

`playwright` lives in `[dependency-groups] dev`, never in `dependencies`: the
distribution must not grow a browser dependency. If it (or its chromium build) is
missing, this whole directory is skipped rather than failed, so `uv run pytest
tests/` stays green on a bare checkout.

    uv run playwright install chromium     # one-off, to enable these tests
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tools" / "fixtures" / "self"
BASELINE = Path(__file__).resolve().parent / "baseline"
SHOTS = Path(__file__).resolve().parent / "shots"
VIEWS = ("timeline", "frontier", "provenance", "clusters")
VIEWPORT = {"width": 1440, "height": 900}

try:  # a bare checkout has no playwright — skip collection, do not error
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - exercised only without the dev group
    collect_ignore_glob = ["test_*.py"]
    sync_playwright = None

_spec = importlib.util.spec_from_file_location("hypergraph_browser", ROOT / "tools" / "hypergraph.py")
hg = importlib.util.module_from_spec(_spec)
sys.modules["hypergraph_browser"] = hg
_spec.loader.exec_module(hg)


def updating() -> bool:
    """Baselines are re-blessed deliberately, so the change shows up in a diff."""
    return os.environ.get("HG_VIZ_UPDATE_BASELINE") == "1"


@pytest.fixture(scope="session")
def viz_html(tmp_path_factory) -> Path:
    """The page under test, built from the frozen `self` fixture via --dev sources."""
    out = tmp_path_factory.mktemp("viz") / "viz.html"
    out.write_text(hg.render_viz(FIXTURE / "record.json", FIXTURE / "state.json",
                                 template=hg.assemble_viz_template()))
    return out


@pytest.fixture(scope="session")
def browser():
    if sync_playwright is None:  # pragma: no cover - collection is ignored above
        pytest.skip("playwright not installed")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binaries not downloaded
            pytest.skip(f"chromium unavailable ({exc.__class__.__name__}); "
                        "run `uv run playwright install chromium`")
        yield b
        b.close()


@pytest.fixture
def page(browser, viz_html):
    ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1,
                              color_scheme="light", reduced_motion="reduce")
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(f"file://{viz_html}")
    pg.wait_for_selector("#world")
    pg.errors = errors
    yield pg
    ctx.close()


def open_view(pg, view: str) -> None:
    """Select a view by its chip and wait for the re-render to settle."""
    pg.click(f'#presets button[data-preset="{view}"]')
    pg.wait_for_function("() => document.querySelectorAll('#nodes g.node').length > 0")
    pg.wait_for_timeout(120)


# Measured through the DOM the page actually produced — no test-only hooks in the
# page itself. `scale` is the fit zoom, and width/height the world bounding box,
# so an unreadable ribbon shows up as a scale near zero and a huge aspect ratio.
METRICS_JS = """() => {
  const world = document.getElementById("world");
  const t = world.getAttribute("transform") || "";
  const m = /scale\\(([-0-9.]+)\\)/.exec(t);
  const bb = world.getBBox();
  const labels = [...document.querySelectorAll("#nodes text")];
  return {
    nodes: document.querySelectorAll("#nodes g.node").length,
    edges: document.querySelectorAll("#edges path").length,
    crosslinks: document.querySelectorAll("#crosslinks path").length,
    blobs: document.querySelectorAll("#blobs path").length,
    labels: labels.length,
    scale: Math.round((m ? +m[1] : 1) * 1000) / 1000,
    width: Math.round(bb.width),
    height: Math.round(bb.height),
  };
}"""


def measure(pg) -> dict:
    m = pg.evaluate(METRICS_JS)
    m["aspect"] = round(m["width"] / max(1, m["height"]), 2)
    return m


def shoot(pg, name: str) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name}.png"
    pg.screenshot(path=str(path))
    return path


def load_baseline() -> dict:
    path = BASELINE / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_baseline(data: dict) -> None:
    BASELINE.mkdir(parents=True, exist_ok=True)
    (BASELINE / "metrics.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
