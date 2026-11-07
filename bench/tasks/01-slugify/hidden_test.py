from textkit.text import slugify

def test_basic():
    assert slugify("Héllo World!") == "hello-world"

def test_runs_and_edges():
    assert slugify("  a  b  ") == "a-b"
    assert slugify("Rock & Roll") == "rock-roll"
    assert slugify("---") == ""
    assert slugify("") == ""

def test_digits_kept():
    assert slugify("Python 3.12 Release") == "python-3-12-release"
