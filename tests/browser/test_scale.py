"""The 500-node scale target, measured in a real browser.

`tools/fixtures/large/` is a synthetic graph at the size the viz is meant to
survive: 500 record nodes, 60 state nodes, ~1000 impact links. It is generated
deterministically (`generate.py`), so this timing stays comparable run to run.
"""
import time

import pytest

from conftest import ROOT, VIEWPORT, hg, measure, open_view

LARGE = ROOT / "tools" / "fixtures" / "large"
# Generous against the measured ~0.45s: this guards against a return of the
# O(n^2) behaviour (which was 8.2s), not against a 20% regression on one machine.
FIRST_PAINT_BUDGET = 1.5


@pytest.fixture(scope="module")
def large_html(tmp_path_factory):
    out = tmp_path_factory.mktemp("large") / "viz.html"
    out.write_text(hg.render_viz(LARGE / "record.json", LARGE / "state.json",
                                 template=hg.assemble_viz_template()))
    return out


@pytest.fixture
def large_page(browser, large_html):
    ctx = browser.new_context(viewport=VIEWPORT, color_scheme="light")
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    ctx.close()


def test_five_hundred_nodes_paint_within_budget(large_page, large_html):
    """First paint is the Everything view — both graphs, blobs and every ribbon.
    That is the heaviest thing the page draws, and now the thing it opens with."""
    started = time.time()
    large_page.goto(f"file://{large_html}")
    large_page.wait_for_selector("#nodes g.node", timeout=60_000)
    elapsed = time.time() - started
    m = measure(large_page)
    assert m["nodes"] == 560 and m["blobs"] == 59   # 500 record + 60 state
    assert large_page.errors == []
    assert elapsed < FIRST_PAINT_BUDGET, (
        f"first paint took {elapsed:.2f}s for 500 nodes and 59 blobs "
        f"(budget {FIRST_PAINT_BUDGET}s)")


def test_every_view_stays_pannable_at_five_hundred_nodes(large_page, large_html):
    large_page.goto(f"file://{large_html}")
    large_page.wait_for_selector("#world")
    for view in ("timeline", "frontier", "provenance", "clusters"):
        started = time.time()
        open_view(large_page, view)
        assert time.time() - started < FIRST_PAINT_BUDGET + 0.2, f"{view} is slow"
        assert measure(large_page)["scale"] >= 0.45


def test_time_window_shrinks_the_world(large_page, large_html):
    """87,000px of timeline is not a drawing. The window makes it one."""
    large_page.goto(f"file://{large_html}")
    large_page.wait_for_selector("#world")
    open_view(large_page, "timeline")
    everything = measure(large_page)
    assert everything["nodes"] == 500
    large_page.click('.seg[data-key="window"] button[data-val="100"]')
    large_page.wait_for_timeout(200)
    windowed = measure(large_page)
    assert windowed["nodes"] == 100
    assert windowed["width"] < everything["width"] / 4


def test_collapsing_a_claim_replaces_its_members_with_one_puck(large_page, large_html):
    large_page.goto(f"file://{large_html}")
    large_page.wait_for_selector("#world")
    open_view(large_page, "clusters")
    before = measure(large_page)
    large_page.click("#blobs text >> nth=0")
    large_page.wait_for_timeout(150)
    button = large_page.query_selector("button[data-collapse]")
    assert button, "a claim with an impact set offers to collapse"
    state = button.get_attribute("data-collapse")
    button.click()
    large_page.wait_for_timeout(500)
    after = measure(large_page)
    assert after["nodes"] < before["nodes"], "members folded away"
    assert after["blobs"] == before["blobs"] - 1, "the collapsed blob is gone"
    assert large_page.is_visible(f'#nodes g.node[data-slug="puck:{state}"]')
    # …and back again
    large_page.query_selector("button[data-collapse]").click()
    large_page.wait_for_timeout(500)
    assert measure(large_page)["nodes"] == before["nodes"]
