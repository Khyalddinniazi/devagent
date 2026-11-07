from shop.cart import Cart

def test_default_unchanged():
    cart = Cart()
    cart.add("a", 2.5, qty=2)
    assert cart.total() == 5.0

def test_tax_after_discount():
    cart = Cart()
    cart.add("a", 100.0)
    cart.apply_discount(10)
    assert cart.total(tax_rate=0.08) == 97.2

def test_half_up():
    cart = Cart()
    cart.add("a", 10.0)
    assert cart.total(tax_rate=0.0125) == 10.13
    cart2 = Cart()
    cart2.add("a", 0.125)
    assert cart2.total() == 0.13
