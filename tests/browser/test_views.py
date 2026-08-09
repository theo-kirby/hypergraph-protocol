"""Layout regression guard: measure every view in a real browser, compare, shoot.

The numbers are deliberately coarse — node/edge/blob/label counts, the fit zoom,
and the world bounding box. That is enough to catch "the layout changed" without
being a pixel-diff that breaks on a font update. Baselines are re-blessed on
purpose, so a layout change shows up as a reviewable diff in
`tests/browser/baseline/metrics.json`:

    HG_VIZ_UPDATE_BASELINE=1 uv run pytest tests/browser/

PNG screenshots land in `tests/browser/shots/` (git-ignored) for eyeballing the
before/after of a phase.
"""
import pytest

from conftest import (VIEWS, load_baseline, measure, open_view, save_baseline,
                      shoot, updating)

# Counts must match exactly; geometry is allowed to wobble by this fraction,
# because text metrics differ slightly between chromium builds.
GEOM_TOLERANCE = 0.02
EXACT = ("nodes", "edges", "blobs", "labels")
GEOM = ("scale", "width", "height")


def test_page_loads_without_errors(page):
    open_view(page, "timeline")
    assert page.errors == []


def test_every_view_matches_its_baseline(page):
    baseline, fresh, failures = load_baseline(), {}, []
    for view in VIEWS:
        open_view(page, view)
        m = measure(page)
        fresh[view] = m
        shoot(page, view)
        want = baseline.get(view)
        if want is None:
            continue
        for key in EXACT:
            if m[key] != want[key]:
                failures.append(f"{view}.{key}: {want[key]} -> {m[key]}")
        for key in GEOM:
            lo, hi = want[key] * (1 - GEOM_TOLERANCE), want[key] * (1 + GEOM_TOLERANCE)
            if not (lo <= m[key] <= hi):
                failures.append(f"{view}.{key}: {want[key]} -> {m[key]}")

    if updating() or not baseline:
        save_baseline(fresh)
        if not baseline:
            pytest.skip("wrote the first metrics baseline; re-run to compare")
        return
    assert not failures, (
        "view layout changed:\n  " + "\n  ".join(failures) +
        "\nIf this is the intended change, re-bless with "
        "HG_VIZ_UPDATE_BASELINE=1 uv run pytest tests/browser/")


def test_no_view_fits_below_the_zoom_floor(page):
    """The defect this overhaul exists to kill: a view that fits by shrinking to
    illegibility. Nothing may open below MIN_FIT — it scrolls instead."""
    for view in VIEWS:
        open_view(page, view)
        assert measure(page)["scale"] >= 0.45, f"{view} opened below the zoom floor"


def test_timeline_x_axis_modes_and_board_tree_toggle(page):
    """The two layout-local toggles both render and both stay above the floor."""
    open_view(page, "timeline")
    rank = measure(page)
    page.click('.seg[data-key="xaxis"] button[data-val="time"]')
    page.wait_for_timeout(120)
    time_mode = measure(page)
    assert time_mode["nodes"] == rank["nodes"]
    # real dates stretch the strip: idle gaps are compressed, not erased
    assert time_mode["width"] > rank["width"]
    assert time_mode["scale"] >= 0.45

    open_view(page, "frontier")
    status = measure(page)
    page.click('.seg[data-key="board"] button[data-val="tree"]')
    page.wait_for_timeout(120)
    tree = measure(page)
    assert tree["nodes"] == status["nodes"]
    assert tree["width"] < status["width"], "the tree is one indented column"
    assert tree["scale"] >= 0.45


def test_layout_local_controls_are_hidden_where_they_mean_nothing(page):
    open_view(page, "timeline")
    assert page.is_visible('.seg[data-key="xaxis"]')
    assert page.is_hidden('.seg[data-key="board"]')
    open_view(page, "frontier")
    assert page.is_hidden('.seg[data-key="xaxis"]')
    assert page.is_visible('.seg[data-key="board"]')
    open_view(page, "clusters")
    assert page.is_hidden('.seg[data-key="xaxis"]')
    assert page.is_hidden('.seg[data-key="board"]')


def test_clusters_draws_distinguishable_labelled_blobs(page):
    """Phase 2's acceptance: one blob per hyperedge, each labelled, and the
    outlines reproduce exactly — the geometry has no randomness in it."""
    open_view(page, "clusters")
    m = measure(page)
    assert m["blobs"] == 12, "one outline per hyperedge"
    assert m["labels"] == m["nodes"], "the circle style is labelled now"
    blob_svg = page.evaluate('() => document.getElementById("blobs").innerHTML')
    # a hull would be a handful of curves; the traced field is far more detailed
    assert blob_svg.count(" C ") > 200, "outlines look like hulls, not a field"
    page.reload()
    page.wait_for_selector("#world")
    open_view(page, "clusters")
    assert page.evaluate('() => document.getElementById("blobs").innerHTML') == blob_svg


def test_blob_labels_do_not_collide(page):
    open_view(page, "clusters")
    boxes = page.evaluate("""() => [...document.querySelectorAll("#blobs text")]
        .map(t => { const b = t.getBBox(); return [b.x, b.y, b.width, b.height]; })""")
    assert len(boxes) == 12
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            apart = (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                     or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])
            assert apart, f"blob labels overlap: {a} vs {b}"


def test_views_are_deterministic_across_reloads(page, viz_html):
    """Two renders of one input must agree — the page has no randomness."""
    first = {}
    for view in VIEWS:
        open_view(page, view)
        first[view] = measure(page)
    page.reload()
    page.wait_for_selector("#world")
    for view in VIEWS:
        open_view(page, view)
        assert measure(page) == first[view], f"{view} is not reproducible"
