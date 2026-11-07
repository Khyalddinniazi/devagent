import json
from shop.cart import Cart

def make():
    cart = Cart()
    cart.add("a", 1.5, qty=2)
    cart.add("b", 3.0)
    cart.apply_discount(15)
    return cart

def test_shape():
    assert make().to_dict() == {
        "items": [{"sku": "a", "price": 1.5, "qty": 2}, {"sku": "b", "price": 3.0, "qty": 1}],
        "discount_percent": 15,
    }

def test_round_trip_through_json():
    cart = make()
    loaded = Cart.from_dict(json.loads(json.dumps(cart.to_dict())))
    assert loaded == cart and loaded.total() == cart.total()

def test_empty():
    assert Cart.from_dict(Cart().to_dict()) == Cart()
