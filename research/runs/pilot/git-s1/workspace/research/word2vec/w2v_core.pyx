# cython: boundscheck=False, wraparound=False, initializedcheck=False, cdivision=True, language_level=3
"""Skip-gram with negative sampling training core in Cython."""

import numpy as np
cimport numpy as np
cimport cython
from libc.math cimport exp, sqrt, log
from libc.stdlib cimport rand, RAND_MAX, srand, malloc, free
from libc.string cimport memset

ctypedef np.float32_t DTYPE_t
ctypedef np.int32_t ITYPE_t


cdef inline float sigmoid(float x) noexcept nogil:
    return 1.0 / (1.0 + exp(-x))


cdef inline int rand_int(int max_val) noexcept nogil:
    """Fast random integer in [0, max_val)."""
    return (rand() % max_val)


@cython.boundscheck(False)
@cython.wraparound(False)
@cython.nonecheck(False)
cdef void train_step(
    int center,
    int context,
    int neg_count,
    float alpha,
    float[:, ::1] W_in,
    float[:, ::1] W_out,
    int dim,
    int[::1] negtable,
    int negtable_size,
) noexcept nogil:
    """Single training step: one positive + neg_count negative samples."""
    cdef int d, n, neg_word, label
    cdef float dot, g
    cdef float neu1[200]  # stack-allocated; increase if dim > 200

    # Positive sample (label = 1)
    dot = 0.0
    for d in range(dim):
        dot += W_in[center, d] * W_out[context, d]
    g = (1.0 - sigmoid(dot)) * alpha
    for d in range(dim):
        # Store contribution to input gradient for reuse in negatives
        neu1[d] = g * W_out[context, d]
        W_out[context, d] += g * W_in[center, d]
    for d in range(dim):
        W_in[center, d] += neu1[d]

    # Negative samples (label = 0)
    for n in range(neg_count):
        neg_word = negtable[rand_int(negtable_size)]
        if neg_word == context:
            continue
        dot = 0.0
        for d in range(dim):
            dot += W_in[center, d] * W_out[neg_word, d]
        g = (0.0 - sigmoid(dot)) * alpha
        for d in range(dim):
            neu1[d] = g * W_out[neg_word, d]
            W_out[neg_word, d] += g * W_in[center, d]
        for d in range(dim):
            W_in[center, d] += neu1[d]


def train(
    np.ndarray[ITYPE_t, ndim=1, mode='c'] data,
    int vocab_size,
    int dim,
    int window,
    int neg_samples,
    int epochs,
    float alpha_start,
    float alpha_end,
    int seed,
    np.ndarray[ITYPE_t, ndim=1, mode='c'] negtable,
    np.ndarray[DTYPE_t, ndim=1, mode='c'] subsample_prob,
):
    """
    Train skip-gram with negative sampling.

    Parameters
    ----------
    data : int array of word indices
    vocab_size : int
    dim : vector dimension
    window : context window size
    neg_samples : number of negative samples per positive
    epochs : number of training epochs
    alpha_start : initial learning rate
    alpha_end : final learning rate (linear decay)
    seed : random seed
    negtable : precomputed negative sampling table (indices into vocab)
    subsample_prob : P(keep) for each word; words with prob < 1 may be discarded
    """
    cdef int data_len = data.shape[0]
    cdef int negtable_size = negtable.shape[0]
    cdef int total_words = 0
    cdef int i, j, k, epoch, center, context, win, word_count
    cdef float alpha, progress
    cdef float rand_val
    cdef np.ndarray[DTYPE_t, ndim=2, mode='c'] W_in_np, W_out_np
    cdef float[:, ::1] W_in, W_out
    cdef int[::1] data_view
    cdef int[::1] negtable_view
    cdef float[::1] subsample_view

    srand(seed)

    # Initialize vectors with small random values
    np.random.seed(seed)
    W_in_np = np.random.uniform(-0.5 / dim, 0.5 / dim, (vocab_size, dim)).astype(np.float32)
    W_out_np = np.zeros((vocab_size, dim), dtype=np.float32)

    W_in = W_in_np
    W_out = W_out_np
    data_view = data
    negtable_view = negtable
    subsample_view = subsample_prob

    cdef float total_tokens = <float>(data_len * epochs)
    cdef int tokens_processed = 0

    for epoch in range(epochs):
        word_count = 0
        for i in range(data_len):
            center = data_view[i]

            # Subsampling check
            if subsample_view[center] < 1.0:
                rand_val = <float>rand() / <float>RAND_MAX
                if rand_val > subsample_view[center]:
                    continue

            word_count += 1
            tokens_processed += 1

            # Linear learning rate decay
            progress = <float>tokens_processed / total_tokens
            alpha = alpha_start + (alpha_end - alpha_start) * progress
            if alpha < alpha_end:
                alpha = alpha_end

            # Random window size in [1, window]
            win = rand_int(window) + 1

            # Iterate over context words
            for j in range(i - win, i + win + 1):
                if j == i or j < 0 or j >= data_len:
                    continue
                context = data_view[j]
                train_step(
                    center, context, neg_samples, alpha,
                    W_in, W_out, dim,
                    negtable_view, negtable_size,
                )

    return W_in_np, W_out_np