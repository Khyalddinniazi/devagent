from textkit.text import is_palindrome

def test_true():
    assert is_palindrome("A man, a plan, a canal: Panama")
    assert is_palindrome("No 'x' in Nixon")
    assert is_palindrome("")
    assert is_palindrome("12321")

def test_false():
    assert not is_palindrome("hello")
    assert not is_palindrome("ab")
