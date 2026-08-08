#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24"]
# ///
"""The frozen fidelity evaluator — scores an arm's vectors, offline and identically.

**This is run by us, never by an arm.** An arm that grades itself measures its
own optimism, so each run hands over `vectors.txt` and this script produces the
number. The arms never see it, and the analogy set is committed alongside it
(`data/questions-words.txt`, 19,544 questions in 14 sections) so the score cannot
drift with a download.

Standard protocol, stated so a reader can check it rather than trust it: an
analogy `a:b::c:d` is answered by the nearest word to `vec(b) - vec(a) + vec(c)`
under cosine similarity, with `a`, `b` and `c` excluded from the candidates.
Questions containing an out-of-vocabulary word are skipped, and the skip count is
reported — a high skip count can flatter accuracy, so it is never hidden.

Everything is lower-cased on both sides. The reference numbers this is compared
against (METRICS.md) come from vanilla SGNS on text8: 24.16% total at dim 100.

    uv run research/eval/analogy.py --vectors run/vectors.txt [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

DATA = Path(__file__).resolve().parent / "data" / "questions-words.txt"

# The five semantic sections; everything else in the file is syntactic (`gram*`).
SEMANTIC_SECTIONS = {
    "capital-common-countries", "capital-world", "currency",
    "city-in-state", "family",
}

# Questions per matrix multiply. 512 x 71k floats is ~290 MB — large enough to
# stay fast, small enough that the whole 19.5k x vocab product is never formed
# (that would be ~11 GB).
BATCH = 512


def load_vectors(path: Path) -> Tuple[Dict[str, int], np.ndarray]:
    """Read word2vec text format and return the index plus L2-normalised rows.

    Tolerant by design: a malformed or short line is skipped rather than fatal,
    because a run that produced *mostly* good vectors should still be scored —
    and a strict parser would hand back a zero that looks like a modelling
    failure instead of a formatting one.
    """
    words: List[str] = []
    rows: List[np.ndarray] = []
    dim = None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline().split()
        # The header is optional: some writers omit it.
        if len(first) == 2 and all(p.isdigit() for p in first):
            dim = int(first[1])
        else:
            fh.seek(0)
        for line in fh:
            parts = line.rstrip().split(" ")
            if len(parts) < 3:
                continue
            word, rest = parts[0], parts[1:]
            if dim is None:
                dim = len(rest)
            if len(rest) != dim:
                continue
            try:
                vec = np.asarray(rest, dtype=np.float32)
            except ValueError:
                continue
            words.append(word.lower())
            rows.append(vec)
    if not rows:
        raise SystemExit(f"no usable vectors in {path}")
    matrix = np.vstack(rows)

    # Diverged training writes NaN or inf, and a silent 0.00% would read as
    # "trained badly" when it means "produced nothing usable" — a different
    # finding. Count it here so the report can say which happened. (Seen live:
    # both git-arm runs wrote 71,290 all-NaN vectors.)
    finite_rows = np.isfinite(matrix).all(axis=1)
    n_bad = int((~finite_rows).sum())

    with np.errstate(over="ignore", invalid="ignore"):
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[~np.isfinite(norms)] = 1.0
    norms[norms == 0] = 1.0
    matrix /= norms
    # Non-finite rows can never match; zero them so they cannot win an argmax.
    matrix[~finite_rows] = 0.0
    load_vectors.last_nonfinite = n_bad  # read by evaluate(); see report below
    # First spelling wins, so a duplicated word cannot silently shift indices.
    index: Dict[str, int] = {}
    for i, w in enumerate(words):
        index.setdefault(w, i)
    return index, matrix


def load_questions(path: Path = DATA) -> List[Tuple[str, Tuple[str, ...]]]:
    out = []
    section = "unknown"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(":"):
            section = line[1:].strip()
            continue
        parts = line.lower().split()
        if len(parts) == 4:
            out.append((section, tuple(parts)))
    return out


def evaluate(index: Dict[str, int], matrix: np.ndarray,
             questions: List[Tuple[str, Tuple[str, ...]]]) -> dict:
    per_section: Dict[str, List[int]] = {}
    skipped_by_section: Dict[str, int] = {}
    usable: List[Tuple[str, Tuple[int, int, int], int]] = []

    for section, (a, b, c, d) in questions:
        ids = [index.get(w) for w in (a, b, c, d)]
        if any(i is None for i in ids):
            skipped_by_section[section] = skipped_by_section.get(section, 0) + 1
            continue
        usable.append((section, (ids[0], ids[1], ids[2]), ids[3]))

    for start in range(0, len(usable), BATCH):
        chunk = usable[start:start + BATCH]
        a_idx = np.array([q[1][0] for q in chunk])
        b_idx = np.array([q[1][1] for q in chunk])
        c_idx = np.array([q[1][2] for q in chunk])
        targets = matrix[b_idx] - matrix[a_idx] + matrix[c_idx]
        n = np.linalg.norm(targets, axis=1, keepdims=True)
        n[n == 0] = 1.0
        targets /= n
        sims = targets @ matrix.T
        # Exclude the three given words, per the standard protocol.
        rows = np.arange(len(chunk))
        for col in (a_idx, b_idx, c_idx):
            sims[rows, col] = -np.inf
        predicted = np.argmax(sims, axis=1)
        for (section, _, gold), pred in zip(chunk, predicted):
            per_section.setdefault(section, []).append(int(pred == gold))

    def summarise(sections) -> dict:
        hits = sum(sum(per_section.get(s, [])) for s in sections)
        total = sum(len(per_section.get(s, [])) for s in sections)
        return {
            "correct": hits, "answered": total,
            "accuracy": (hits / total) if total else 0.0,
        }

    all_sections = set(per_section) | set(skipped_by_section)
    semantic = [s for s in all_sections if s in SEMANTIC_SECTIONS]
    syntactic = [s for s in all_sections if s not in SEMANTIC_SECTIONS]

    nonfinite = int(getattr(load_vectors, "last_nonfinite", 0))
    return {
        "dim": int(matrix.shape[1]),
        "vocab": int(matrix.shape[0]),
        "nonfinite_vectors": nonfinite,
        "diverged": bool(nonfinite and nonfinite >= 0.5 * matrix.shape[0]),
        "total": summarise(all_sections),
        "semantic": summarise(semantic),
        "syntactic": summarise(syntactic),
        "skipped": sum(skipped_by_section.values()),
        "questions": len(questions),
        "per_section": {
            s: {"correct": sum(v), "answered": len(v),
                "accuracy": (sum(v) / len(v)) if v else 0.0,
                "skipped": skipped_by_section.get(s, 0)}
            for s, v in sorted(per_section.items())
        },
    }


def score_bands(report: dict) -> dict:
    """Apply METRICS.md's pre-registered bands. Thresholds live here, once."""
    acc = report["total"]["accuracy"]
    dim_ok = report["dim"] >= 100
    if report.get("diverged"):
        # Diverged training is not a low score; it is an absent one.
        return {"reproduced": False, "matched_literature": False,
                "diverged": True,
                "literature_reference_dim100": 0.2416}
    return {
        "reproduced": bool(acc >= 0.20 and dim_ok),
        "matched_literature": bool(acc >= 0.2416 and dim_ok),
        "literature_reference_dim100": 0.2416,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--vectors", required=True, type=Path)
    p.add_argument("--questions", type=Path, default=DATA)
    p.add_argument("--json", type=Path, help="write the full report here")
    args = p.parse_args(argv)

    index, matrix = load_vectors(args.vectors)
    report = evaluate(index, matrix, load_questions(args.questions))
    report["bands"] = score_bands(report)

    t, s, y = report["total"], report["semantic"], report["syntactic"]
    print(f"vectors:    {report['vocab']} words, dim {report['dim']}")
    if report.get("nonfinite_vectors"):
        print(f"WARNING:    {report['nonfinite_vectors']} of {report['vocab']} "
              f"vectors are NaN/inf"
              + ("  -> TRAINING DIVERGED" if report.get("diverged") else ""))
    print(f"answered:   {t['answered']} of {report['questions']} "
          f"({report['skipped']} skipped for OOV)")
    print(f"semantic:   {s['accuracy']:6.2%}  ({s['correct']}/{s['answered']})")
    print(f"syntactic:  {y['accuracy']:6.2%}  ({y['correct']}/{y['answered']})")
    print(f"TOTAL:      {t['accuracy']:6.2%}  ({t['correct']}/{t['answered']})")
    b = report["bands"]
    print(f"bands:      reproduced={b['reproduced']} "
          f"matched_literature={b['matched_literature']} "
          f"(reference {b['literature_reference_dim100']:.2%} at dim 100)")
    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
