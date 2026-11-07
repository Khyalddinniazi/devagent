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

    def to_dict(self) -> dict:
        return {
            "items": [{"sku": i.sku, "price": i.price, "qty": i.qty} for i in self.items.values()],
            "discount_percent": self.discount_percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Cart:
        items = {i["sku"]: Item(i["sku"], i["price"], i["qty"]) for i in data["items"]}
        return cls(items=items, discount_percent=data["discount_percent"])
