import pytest
from shop.cart import Cart

def test_rejects_out_of_range():
    cart = Cart()
    cart.add("x", 10.0)
    cart.apply_discount(20)
    for bad in (150, -5, 100.01):
        with pytest.raises(ValueError):
            cart.apply_discount(bad)
    assert cart.total() == 8.0

def test_bounds_ok():
    cart = Cart()
    cart.add("x", 10.0)
    cart.apply_discount(100)
    assert cart.total() == 0.0
    cart.apply_discount(0)
    assert cart.total() == 10.0
