from textkit.text import word_frequencies

def test_counts():
    assert word_frequencies("Hello, hello! It's me.") == {"hello": 2, "it's": 1, "me": 1}

def test_empty():
    assert word_frequencies("") == {}
    assert word_frequencies("... !!!") == {}

def test_digits():
    assert word_frequencies("2 cats, 2 dogs") == {"2": 2, "cats": 1, "dogs": 1}
