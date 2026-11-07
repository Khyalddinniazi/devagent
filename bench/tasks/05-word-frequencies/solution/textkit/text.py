"""Small text helpers."""

import re


def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


def word_frequencies(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in re.findall(r"[a-z0-9']+", text.lower()):
        counts[word] = counts.get(word, 0) + 1
    return counts
