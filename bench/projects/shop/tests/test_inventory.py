from shop.inventory import Inventory


def test_restock_and_reserve():
    inv = Inventory()
    inv.restock("apple", 5)
    inv.reserve("apple", 2)
    assert inv.available("apple") == 3
