from shop.inventory import Inventory

def test_low_stock():
    inv = Inventory()
    for sku, n in [("pear", 2), ("apple", 10), ("fig", 1), ("kiwi", 5)]:
        inv.restock(sku, n)
    inv.reserve("fig", 1)
    assert inv.low_stock(5) == ["fig", "pear"]
    assert inv.low_stock(1) == ["fig"]
    assert inv.low_stock(100) == ["apple", "fig", "kiwi", "pear"]

def test_empty():
    assert Inventory().low_stock(3) == []
