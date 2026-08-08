# Dead ends and failures

## In-place gradient updates cause numerical divergence (FIXED)

**What we tried:** Original training loop updated W_in[center] immediately after each positive/negative sample, using already-modified values for W_out updates in the same context window.

**Why it failed:** After ~2000s of training, the vectors were entirely inf/-inf/nan, yielding 0.0 accuracy on all analogy categories (0/9310 correct). The in-place update creates a positive feedback loop: each gradient step modifies W_in, which then feeds into the next gradient computation, amplifying the signal unboundedly.

**Fix:** Added neu1e gradient accumulation buffer. Gradient for W_in is accumulated separately and applied only after all context words for a center word are processed. W_out updates always use the original (pre-update) W_in values. This matches the original word2vec.c design.

**Lesson:** When implementing gradient-based algorithms from papers, match the reference implementation's gradient accumulation strategy exactly. Subtle differences in update ordering can cause catastrophic numerical failure.