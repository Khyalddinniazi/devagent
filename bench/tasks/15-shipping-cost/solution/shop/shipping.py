"""Shipping cost rules."""


def shipping_cost(subtotal: float, country: str) -> float:
    if subtotal < 0:
        raise ValueError("subtotal must not be negative")
    if len(country) != 2 or not country.isalpha():
        raise ValueError("country must be a two-letter code")
    code = country.upper()
    if code == "US":
        return 0.0 if subtotal >= 50 else 5.0
    if code in {"DE", "FR", "NL"}:
        return 9.5
    return 15.0
