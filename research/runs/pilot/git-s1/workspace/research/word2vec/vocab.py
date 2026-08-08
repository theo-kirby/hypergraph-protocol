"""Vocabulary building for word2vec: reading text8, building vocab, subsampling, negative sampling table."""

import numpy as np
from collections import Counter


def build_vocab(filepath, min_count=5):
    """
    Read corpus and build vocabulary.

    Returns
    -------
    word2id : dict
    id2word : list
    counts : list of ints
    data : np.ndarray of int32 word indices (the full corpus)
    """
    print(f"Reading corpus from {filepath}...")
    with open(filepath, "r") as f:
        text = f.read()

    words = text.split()
    print(f"Total tokens: {len(words)}")

    # Count
    print("Counting word frequencies...")
    counter = Counter(words)
    total_words = len(words)
    del words, text  # free memory

    # Filter by min_count
    vocab = {w: c for w, c in counter.items() if c >= min_count}
    print(
        f"Vocabulary size (min_count={min_count}): {len(vocab)} "
        f"({total_words - sum(vocab.values())} tokens dropped)"
    )

    word2id = {w: i for i, w in enumerate(vocab.keys())}
    id2word = list(vocab.keys())
    counts = [vocab[w] for w in id2word]

    return word2id, id2word, counts, len(id2word)


def corpus_to_ids(filepath, word2id):
    """Convert corpus to numpy int32 array of word indices, skipping OOV words."""
    print(f"Converting corpus to word IDs...")
    with open(filepath, "r") as f:
        text = f.read()
    words = text.split()
    data = []
    unk_count = 0
    for w in words:
        idx = word2id.get(w)
        if idx is not None:
            data.append(idx)
        else:
            unk_count += 1
    print(f"Tokens in vocabulary: {len(data)}, out-of-vocabulary: {unk_count}")
    return np.array(data, dtype=np.int32)


def build_subsample_prob(counts, threshold):
    """
    Compute subsampling probabilities: P(keep) for each word.

    Formula from the paper: P(wi) = 1 - sqrt(t / f(wi))
    where f is the normalized frequency, clamp to 0.
    For efficiency we store P(keep). Words with freq < t have P(keep)=1.0.
    Actually the paper discards with probability: 1 - sqrt(t/f).
    So P(keep) = min(1, sqrt(t/f) + t/f) ... no.

    The subsampling formula: p_discard = 1 - sqrt(threshold / freq)
    So p_keep = 1 - p_discard = sqrt(threshold / freq)

    But only applied when freq > threshold. So:
    p_keep = sqrt(threshold / freq)  if freq > threshold else 1.0
    """
    total = sum(counts)
    freq = np.array(counts, dtype=np.float64) / total
    prob = np.ones(len(counts), dtype=np.float32)
    t = threshold
    for i, f in enumerate(freq):
        if f > t:
            prob[i] = np.sqrt(t / f)
    print(
        f"Subsampling threshold {threshold}: "
        f"{(prob < 1.0).sum()} words affected, "
        f"P(keep) range: [{prob.min():.4f}, {prob.max():.4f}]"
    )
    return prob


def build_neg_table(counts, table_size=100_000_000):
    """
    Build negative sampling table with unigram distribution raised to 3/4.

    Returns np.array of int32 word indices.
    """
    print(f"Building negative sampling table (size={table_size})...")
    # Unigram ^ 3/4
    power = np.array(counts, dtype=np.float64) ** 0.75
    total = power.sum()
    probabilities = power / total

    table = np.zeros(table_size, dtype=np.int32)
    vocab_size = len(counts)
    cumulative = 0.0
    idx = 0
    for i in range(vocab_size):
        cumulative += probabilities[i] * table_size
        next_idx = int(cumulative)
        table[idx:next_idx] = i
        idx = next_idx
    # Fill any remainder
    table[idx:] = vocab_size - 1
    np.random.shuffle(table)  # Reduce sequential bias
    print("Negative sampling table built.")
    return table