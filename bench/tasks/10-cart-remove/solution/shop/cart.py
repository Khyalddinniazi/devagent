"""Shopping cart."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    sku: str
    price: float
    qty: int = 1


@dataclass
class Cart:
    items: dict[str, Item] = field(default_factory=dict)
    discount_percent: float = 0.0

    def add(self, sku: str, price: float, qty: int = 1) -> None:
        if qty < 1:
            raise ValueError("qty must be at least 1")
        self.items[sku] = Item(sku, price, qty)

    def apply_discount(self, percent: float) -> None:
        self.discount_percent = percent

    def subtotal(self) -> float:
        return sum(i.price * i.qty for i in self.items.values())

    def total(self) -> float:
        return round(self.subtotal() * (1 - self.discount_percent / 100), 2)

    def remove(self, sku: str, qty: int | None = None) -> None:
        if sku not in self.items:
            raise KeyError(sku)
        if qty is None:
            del self.items[sku]
            return
        if qty < 1:
            raise ValueError("qty must be at least 1")
        self.items[sku].qty -= qty
        if self.items[sku].qty <= 0:
            del self.items[sku]
