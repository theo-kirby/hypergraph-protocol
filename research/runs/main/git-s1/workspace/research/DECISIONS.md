# Design Decisions

## Cython for the inner training loop

**Decision:** Use Cython with `nogil` for the skip-gram training loop.
**Rationale:** Pure Python is too slow for 17M tokens × 5 epochs × (1+15) samples.
Cython gives near-C speed with Python interop. NumPy alone can't express this
efficiently because the loop is inherently sequential (each update depends on
previous ones through shared parameters).

**Rejected:** PyTorch — no GPU on this machine, CPU overhead is high for this
task. Pure NumPy vectorized — not feasible for the dynamic, sequential nature
of skip-gram training.

## W_out initialized to zeros

**Decision:** Initialize output (context) vectors to zeros.
**Rationale:** This is a deviation from the original word2vec which initializes
both input and output randomly. The current code was written this way.
**Concern:** With W_out=0, W_in doesn't update during the first few updates
to each target word. This may slow convergence and could theoretically cause
instability, though the successful run showed it works adequately.

**TODO:** Test random W_out initialization and compare.

## Negative sampling vs hierarchical softmax

**Decision:** Use negative sampling with 15 negatives.
**Rationale:** Negative sampling is simpler to implement, faster, and the
original paper showed it works well. Hierarchical softmax adds complexity
(Huffman tree) without clear benefit for this scale.

## Subsampling threshold 1e-5

**Decision:** Use 1e-5 as the subsampling threshold.
**Rationale:** This is the value from the original word2vec paper and code.
With text8's frequency distribution, this causes ~8,174 words (out of 71,290)
to be subsampled, which covers the most frequent words that dominate context
windows.