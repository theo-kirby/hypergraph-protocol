## Your memory system: git and files

Your memory is **the git repository itself** — its history, and a small set of
files you maintain inside it. Nothing else records what you did. Use it
deliberately, as a research log, not as a place to dump code at the end.

### The unit of record: a commit

One commit is one coherent step: a baseline that works, one experiment, one fix,
one decision. Commit as you go, never in one batch at the end.

A commit message is a record, not a label. Write them like this:

```
Subsample threshold 1e-4: analogy accuracy 0.31 -> 0.38

Hypothesis: frequent words dominate the context windows, so downsampling
them should sharpen the vectors.
Setup: text8, 5 epochs, dim 200, window 5, 15 negatives, seed 1.
Result: semantic 0.29 -> 0.41, syntactic 0.33 -> 0.36. 12 min on 4 vCPU.
Interpretation: the gain is almost entirely semantic, which matches the
paper's claim. Keeping 1e-4.
```

A one-line message like "fix training" records nothing. State the **change
relative to the previous state**, the **number**, and what it **means**.

### The files you maintain

Keep three living documents at the repo root, updated as you work:

- **`NOTES.md`** — the running research log, newest entry first. One entry per
  step: what you tried, the number you got, what you concluded. This is the file
  a reader opens first.
- **`DECISIONS.md`** — the choices you made and why, including the ones you
  rejected. "Chose X over Y because Z" is the entry. Rationale you do not write
  down is rationale that is lost.
- **`DEAD-ENDS.md`** — everything that did not work, and why. This is the most
  valuable file you will write, because it is the only record of expensive
  knowledge that produced no artifact.

Also keep **`README.md`** current: what this is, the best result so far, and the
exact command to reproduce it.

### Structure: use the repository's shape

- **Branch for alternatives.** When you face a fork — two hypotheses, two
  approaches, an ablation — make a branch per option off the shared parent so the
  alternatives sit side by side and can be compared. Merge the winner back with a
  merge commit whose message states *why* it won.
- **Tag milestones.** `git tag baseline-v1`, `git tag best-so-far` — so you can
  point at a state later, and diff against it.
- **Keep results in the repo.** Write metrics under `artifacts/` and commit them
  alongside the code that produced them, so every number in `NOTES.md` has a file
  behind it in the same commit.
- **Never rewrite history.** No amend, no rebase, no force push. The log is the
  record; editing it destroys evidence.

### Finding things later

The log is also your search index, and you will need it — you will forget what
you tried three hours ago. Learn to interrogate it:

- `git log --oneline` — the shape of the work so far.
- `git log --grep=subsample` — every step that touched an idea, by message.
- `git log --stat -- artifacts/` — when each result file changed, and by how much.
- `git show <sha>` — the full record of one step: message, code, metrics, note.
- `git diff <tag>..HEAD` — everything that changed since a milestone.

This only works if the messages are written as records. A log of "wip", "fix",
"try again" is a log you cannot search, which means it is not memory.

### The loop you run

1. **Orient.** `git log --oneline`, then read `NOTES.md`, `DECISIONS.md`, and
   `DEAD-ENDS.md` before acting. They tell you what has already been tried.
2. **Decide the next step** and why, from what the log shows.
3. **Run it**, writing outputs under `artifacts/`.
4. **Record it**: append to `NOTES.md` (and `DEAD-ENDS.md` if it failed), then
   commit code, artifacts, and notes **together** in one commit with a message
   that states the change and the number.
5. **Push.**

### Rules

- **Commit as you go.** A step that is not committed did not happen, because the
  box can vanish before you commit it.
- **Every empirical commit carries its evidence.** The metrics file goes in the
  same commit as the code and the note. A number in `NOTES.md` with no file
  behind it is not checkable.
- **Every commit message states a result or a decision**, not just an action.
- **Record failures as commits too.** A commit whose message is "Refuted: X does
  not help, accuracy 0.31 -> 0.30, reverting" is a real unit of work.
- **Keep `NOTES.md` current, not perfect.** It is a log, not a paper.
- **Re-read your own notes** when you are unsure whether you tried something. You
  will forget; the file will not.
