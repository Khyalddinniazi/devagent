"""Small text helpers."""


def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


def is_palindrome(text: str) -> bool:
    chars = [c.lower() for c in text if c.isalnum()]
    return chars == chars[::-1]
