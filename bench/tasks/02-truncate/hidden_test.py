import pytest
from textkit.text import truncate

def test_fits():
    assert truncate("hi", 5) == "hi"
    assert truncate("hello", 5) == "hello"

def test_cut():
    assert truncate("hello world", 8) == "hello..."
    assert truncate("abcdef", 4, suffix="…") == "abc…"

def test_too_short():
    with pytest.raises(ValueError):
        truncate("abcdef", 2)
