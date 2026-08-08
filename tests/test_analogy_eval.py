"""Tests for the frozen fidelity evaluator.

The evaluator produces the single number the whole experiment is judged on, so it
is tested against cases with a known answer rather than eyeballed on real output.
A silent bug here — an off-by-one in the exclusion, a mis-split of semantic and
syntactic — would not crash. It would just report a plausible wrong accuracy for
every arm, and nothing downstream would contradict it.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "analogy", ROOT / "research" / "eval" / "analogy.py")
analogy = importlib.util.module_from_spec(_spec)
sys.modules["analogy"] = analogy
_spec.loader.exec_module(analogy)


def write_vectors(tmp_path, mapping, dim):
    lines = [f"{len(mapping)} {dim}"]
    for word, vec in mapping.items():
        lines.append(word + " " + " ".join(f"{v:.6f}" for v in vec))
    path = tmp_path / "vectors.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_perfect_analogies_score_100_percent(tmp_path):
    """Vectors built so b - a + c lands exactly on d must score 1.0."""
    # A clean parallelogram: king - man + woman = queen, in 3 dimensions.
    vecs = {
        "man":   [1.0, 0.0, 0.0],
        "woman": [1.0, 1.0, 0.0],
        "king":  [0.0, 0.0, 1.0],
        "queen": [0.0, 1.0, 1.0],
    }
    path = write_vectors(tmp_path, vecs, 3)
    index, matrix = analogy.load_vectors(path)
    questions = [("family", ("man", "king", "woman", "queen"))]
    report = analogy.evaluate(index, matrix, questions)
    assert report["total"]["answered"] == 1
    assert report["total"]["accuracy"] == 1.0
    assert report["semantic"]["answered"] == 1
    assert report["syntactic"]["answered"] == 0


def test_the_three_given_words_are_excluded(tmp_path):
    """Without the exclusion, the nearest word is usually c itself.

    This is the classic silent failure: leave `c` in the candidate pool and
    accuracy collapses toward zero for reasons that look like bad training.
    """
    # `c` is placed nearest to the query so it would win if not excluded, and the
    # correct answer sits slightly further away.
    vecs = {
        "a": [1.0, 0.0],
        "b": [0.0, 1.0],
        "c": [0.999, 0.001],
        "d": [0.0, 1.0],
    }
    path = write_vectors(tmp_path, vecs, 2)
    index, matrix = analogy.load_vectors(path)
    report = analogy.evaluate(index, matrix, [("family", ("a", "b", "c", "d"))])
    assert report["total"]["accuracy"] == 1.0, "c was not excluded from candidates"


def test_out_of_vocabulary_questions_are_skipped_and_counted(tmp_path):
    """A high skip count flatters accuracy, so it must always be reported."""
    vecs = {"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [1.0, 1.0]}
    path = write_vectors(tmp_path, vecs, 2)
    index, matrix = analogy.load_vectors(path)
    questions = [
        ("family", ("a", "b", "c", "missing")),
        ("family", ("a", "b", "c", "alsomissing")),
    ]
    report = analogy.evaluate(index, matrix, questions)
    assert report["skipped"] == 2
    assert report["total"]["answered"] == 0
    assert report["total"]["accuracy"] == 0.0


def test_semantic_syntactic_split_matches_the_standard_sections():
    """gram* is syntactic; the five named sets are semantic. Nothing else."""
    sections = {s for s, _ in analogy.load_questions()}
    assert analogy.SEMANTIC_SECTIONS <= sections
    syntactic = sections - analogy.SEMANTIC_SECTIONS
    assert syntactic, "no syntactic sections found"
    assert all(s.startswith("gram") for s in syntactic), syntactic


def test_the_committed_analogy_set_is_the_standard_one():
    """19,544 questions in 14 sections — pinned so a score cannot drift."""
    questions = analogy.load_questions()
    assert len(questions) == 19544
    assert len({s for s, _ in questions}) == 14


def test_bands_are_the_preregistered_thresholds():
    """METRICS.md fixes these before any run; they must not drift silently."""
    low_dim = {"dim": 50, "total": {"accuracy": 0.30}}
    assert analogy.score_bands(low_dim)["reproduced"] is False, "dim gate ignored"

    good = {"dim": 100, "total": {"accuracy": 0.25}}
    bands = analogy.score_bands(good)
    assert bands["reproduced"] is True
    assert bands["matched_literature"] is True

    modest = {"dim": 200, "total": {"accuracy": 0.21}}
    bands = analogy.score_bands(modest)
    assert bands["reproduced"] is True
    assert bands["matched_literature"] is False
