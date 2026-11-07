import pytest
from shop.shipping import shipping_cost

def test_us():
    assert shipping_cost(10, "US") == 5.0
    assert shipping_cost(50, "us") == 0.0
    assert shipping_cost(49.99, "US") == 5.0

def test_eu_and_other():
    assert shipping_cost(100, "de") == 9.5
    assert shipping_cost(1, "NL") == 9.5
    assert shipping_cost(1, "JP") == 15.0

def test_invalid():
    for args in [(10, "USA"), (10, ""), (10, "1A"), (-1, "US")]:
        with pytest.raises(ValueError):
            shipping_cost(*args)
