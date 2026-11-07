from shop.cart import Cart

def test_add_twice_accumulates():
    cart = Cart()
    cart.add("pen", 2.0)
    cart.add("pen", 2.0, qty=3)
    assert cart.items["pen"].qty == 4
    assert cart.total() == 8.0

def test_other_items_unaffected():
    cart = Cart()
    cart.add("a", 1.0)
    cart.add("b", 2.0)
    cart.add("a", 1.0)
    assert cart.total() == 4.0
