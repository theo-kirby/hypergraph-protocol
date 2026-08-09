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
