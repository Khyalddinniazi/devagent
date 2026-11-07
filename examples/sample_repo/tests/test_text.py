from sample.text import word_count


def test_word_count():
    assert word_count("hello big world") == 3
    assert word_count("") == 0
