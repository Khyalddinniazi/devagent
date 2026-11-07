import pytest
from textkit.text import wrap

def test_wrap():
    assert wrap("the quick brown fox jumps", 10) == ["the quick", "brown fox", "jumps"]

def test_whitespace_collapsed():
    assert wrap("  a   b \n c ", 3) == ["a b", "c"]

def test_long_word():
    assert wrap("hi extraordinary yo", 5) == ["hi", "extraordinary", "yo"]

def test_empty_and_invalid():
    assert wrap("   ", 4) == []
    with pytest.raises(ValueError):
        wrap("x", 0)
