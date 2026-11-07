"""Small text helpers."""


def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


def truncate(text: str, max_len: int, suffix: str = "...") -> str:
    if len(text) <= max_len:
        return text
    if max_len < len(suffix):
        raise ValueError("max_len is smaller than the suffix")
    return text[: max_len - len(suffix)] + suffix
