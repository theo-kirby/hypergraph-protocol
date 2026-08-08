# Dead Ends

## NaN in all vectors (Session 1)

**What was tried:** Full 5-epoch training run with dim=200, window=5, neg=15,
subsample=1e-5, lr=0.025, seed=42.

**Expected:** Reasonable analogy accuracy (~20-30%).

**What happened:** All vectors became NaN. Total accuracy 0.0%.
Training time was anomalously long (1875s vs 1661s for the working run),
suggesting NaN appeared mid-training and corrupted subsequent computation.

**Investigation:** Re-ran identical code in Session 2 — no NaN, training
completed correctly with 22.03% accuracy. NaN did not reproduce.

**Root cause (likely):** The Cython `.so` file timestamp (21:56) is after the
artifacts timestamp (21:39). The previous session's first run used a `.so`
compiled from an earlier version of the code, possibly with a bug (e.g.,
missing overflow guard in sigmoid, or a memory issue). Recompilation before
Session 2 fixed it.

**Lesson:** Always verify `.so` freshness before trusting results. A `make`-style
build system or hash check would prevent this class of bug.

## (No other dead ends yet — this is the first working baseline)