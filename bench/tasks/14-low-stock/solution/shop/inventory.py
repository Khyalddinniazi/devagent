"""Stock levels per SKU."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when there isn't enough stock for a request."""


class Inventory:
    def __init__(self) -> None:
        self._stock: dict[str, int] = {}

    def restock(self, sku: str, n: int) -> None:
        if n < 1:
            raise ValueError("n must be at least 1")
        self._stock[sku] = self._stock.get(sku, 0) + n

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def reserve(self, sku: str, n: int) -> None:
        self._stock[sku] = self.available(sku) - n

    def low_stock(self, threshold: int) -> list[str]:
        return sorted(sku for sku, n in self._stock.items() if n < threshold)
