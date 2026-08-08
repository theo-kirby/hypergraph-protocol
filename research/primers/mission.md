Your mission: implement **word2vec** from the paper and reproduce its word
analogy result, from scratch, on this box.

**The paper.** Mikolov, Chen, Corrado, Dean (2013), *Efficient Estimation of Word
Representations in Vector Space* (arXiv:1301.3781), together with the negative
sampling procedure from Mikolov et al. (2013), *Distributed Representations of
Words and Phrases and their Compositionality* (arXiv:1310.4546). Implement the
**skip-gram** model trained with **negative sampling**.

**The data.** The `text8` corpus — the standard 100 MB Wikipedia dump, about 17M
words, available at `http://mattmahoney.net/dc/text8.zip`. Build the vocabulary
yourself with a minimum count of 5.

**The evaluation.** The Google word-analogy set (the semantic–syntactic word
relationship test set that accompanies the paper), commonly distributed as
`questions-words.txt`. An analogy `a:b::c:d` is answered by finding the nearest
word to `vec(b) - vec(a) + vec(c)` under cosine similarity, excluding `a`, `b`
and `c` from the candidates. Report **total accuracy**, and the **semantic** and
**syntactic** subsets separately. Skip questions containing a word outside your
vocabulary, and report how many you skipped.

**What you must produce**, in this exact location and format, because it is how
your work is scored:

- `~/research/artifacts/vectors.txt` — your final word vectors in word2vec text
  format. First line: `<vocab_size> <dim>`. Then one line per word:
  the word, then its components, all space-separated.
- `~/research/artifacts/results.json` — your measured accuracies and the
  hyperparameters that produced them (dimension, window, negative samples,
  epochs, subsampling threshold, learning rate, seed, wall-clock training time).

**Constraints.**

- This box has **4 vCPU, 8 GB RAM, and no GPU**. A pure-Python inner training
  loop will not finish in the time you have. Plan for that.
- You have about **3 hours**. Budget it. Getting a complete, honestly-measured,
  modest result is success; an ambitious half-finished one is not.
- Write your own implementation. Do not import `gensim` or any other library
  that already implements word2vec. NumPy, and compiling your own extension, are
  both fine.

**How you will be judged.** On the accuracy you actually reach, on whether a
stranger could reproduce it from what you leave behind, and on how honestly you
recorded what happened — including the parts that did not work. Report the
number you measured, whatever it is. A modest number honestly reported and fully
reproducible beats a better number nobody can check.
