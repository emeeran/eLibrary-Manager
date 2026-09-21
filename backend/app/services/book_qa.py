"""Passage retrieval for "Ask this book" (item 2.1).

The content index stores one flattened text blob per book (no chapter
boundaries), so retrieval scores sliding windows against the question's
terms and returns the top non-overlapping passages. FTS5's bm25 ranks the
whole book equally for any in-book query, so a cheap in-Python scan is both
simpler and better here. 12k-char-plus books scan in microseconds at this
scale; revisit only if per-book content grows by orders of magnitude.
"""

import re

_WORD_RE = re.compile(r"[a-zA-Z']{3,}")

_STOPWORDS = frozenset(
    """the and for are but not you all any can had her was one our out day get has
    him his how man new now old see two way who boy did its let put say she too
    use that this with what when where which while would there their they them
    from have been were will your does about into over under after before between
    book author chapter does did doing done just like some such only also than
    then them these those what when why how whom whose""".split()
)


def question_terms(question: str) -> list[str]:
    """Lowercase content words from the question (stopwords dropped)."""
    return [
        w.lower()
        for w in _WORD_RE.findall(question)
        if w.lower() not in _STOPWORDS
    ]


def select_passages(
    content: str, question: str, k: int = 3, window: int = 1800, step: int = 900
) -> list[str]:
    """Pick the top-k non-overlapping windows of content matching the question.

    Args:
        content: The book's extracted text.
        question: The reader's question.
        k: Number of passages to return.
        window: Window size in characters.
        step: Stride between candidate windows.

    Returns:
        Up to ``k`` passages, best first.
    """
    if not content:
        return []
    terms = question_terms(question)
    if not terms:
        return [content[:window]] if len(content) <= window else [content[:window]]

    # Term frequency per window.
    lower = content.lower()
    scored: list[tuple[int, int]] = []  # (score, start)
    for start in range(0, max(len(content) - window, 1), step):
        chunk = lower[start : start + window]
        score = sum(chunk.count(t) for t in terms)
        if score > 0:
            scored.append((score, start))
    if not scored:
        return []

    # Best windows first; drop overlaps with an already-chosen window.
    scored.sort(reverse=True)
    chosen: list[tuple[int, int]] = []
    for _score, start in scored:
        if all(start >= end or start + window <= begin for begin, end in chosen):
            chosen.append((start, start + window))
        if len(chosen) == k:
            break

    passages = []
    for begin, end in sorted(chosen):
        # Snap to word boundaries.
        while begin > 0 and content[begin - 1].isalnum():
            begin -= 1
        while end < len(content) and content[end].isalnum():
            end += 1
        passages.append(" ".join(content[begin:end].split()))
    return passages
