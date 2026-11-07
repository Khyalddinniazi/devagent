import pytest
from shop.cart import Cart

def make():
    cart = Cart()
    cart.add("a", 1.0, qty=3)
    cart.add("b", 5.0)
    return cart

def test_remove_all():
    cart = make()
    cart.remove("a")
    assert "a" not in cart.items and cart.total() == 5.0

def test_remove_some():
    cart = make()
    cart.remove("a", 2)
    assert cart.items["a"].qty == 1

def test_remove_to_zero():
    cart = make()
    cart.remove("a", 5)
    assert "a" not in cart.items

def test_errors():
    cart = make()
    with pytest.raises(KeyError):
        cart.remove("zzz")
    with pytest.raises(ValueError):
        cart.remove("a", 0)
