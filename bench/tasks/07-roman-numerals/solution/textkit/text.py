"""Small text helpers."""


def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n: int) -> str:
    if not 1 <= n <= 3999:
        raise ValueError("n must be between 1 and 3999")
    out = ""
    for value, sym in _ROMAN:
        count, n = divmod(n, value)
        out += sym * count
    return out


def from_roman(s: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    if not s or any(c not in values for c in s):
        raise ValueError(f"invalid roman numeral: {s!r}")
    total = 0
    for i, c in enumerate(s):
        v = values[c]
        total += -v if i + 1 < len(s) and values[s[i + 1]] > v else v
    if not 1 <= total <= 3999 or to_roman(total) != s:
        raise ValueError(f"invalid roman numeral: {s!r}")
    return total
