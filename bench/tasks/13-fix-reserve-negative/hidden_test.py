import pytest
from shop.inventory import Inventory, OutOfStock

def test_reserve_all_ok():
    inv = Inventory()
    inv.restock("a", 3)
    inv.reserve("a", 3)
    assert inv.available("a") == 0

def test_too_many():
    inv = Inventory()
    inv.restock("a", 2)
    with pytest.raises(OutOfStock):
        inv.reserve("a", 3)
    assert inv.available("a") == 2
    with pytest.raises(OutOfStock):
        inv.reserve("never-stocked", 1)

def test_invalid_n():
    inv = Inventory()
    inv.restock("a", 2)
    with pytest.raises(ValueError):
        inv.reserve("a", 0)
