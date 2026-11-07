"""Shopping cart."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal


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

    def total(self, tax_rate: float = 0.0) -> float:
        sub = sum(Decimal(str(i.price)) * i.qty for i in self.items.values())
        value = sub * (1 - Decimal(str(self.discount_percent)) / 100) * (1 + Decimal(str(tax_rate)))
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
