"""Small text helpers."""


def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines
