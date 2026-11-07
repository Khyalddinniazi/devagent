import pytest
from textkit.text import from_roman, to_roman

def test_to_roman():
    assert to_roman(1994) == "MCMXCIV"
    assert to_roman(3999) == "MMMCMXCIX"
    assert to_roman(4) == "IV"

def test_range():
    for bad in (0, 4000, -1):
        with pytest.raises(ValueError):
            to_roman(bad)

def test_round_trip():
    assert all(from_roman(to_roman(n)) == n for n in range(1, 4000))

def test_invalid():
    for bad in ("IIII", "ABC", "", "IC", "VV"):
        with pytest.raises(ValueError):
            from_roman(bad)
