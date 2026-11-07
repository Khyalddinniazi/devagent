import pytest

from shop.cart import Cart


def test_total_single_item():
    cart = Cart()
    cart.add("apple", 2.5, qty=2)
    assert cart.total() == 5.0


def test_discount():
    cart = Cart()
    cart.add("pen", 10.0)
    cart.apply_discount(10)
    assert cart.total() == 9.0


def test_qty_must_be_positive():
    with pytest.raises(ValueError):
        Cart().add("x", 1.0, qty=0)
