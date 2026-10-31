"""Exact sample prices; no live marketplace feed is configured."""
import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from typing import Protocol

from .ledger import CAP

NANO = 1_000_000_000


def ton_to_nano(value: str) -> int:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('Invalid sample price')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or not Decimal('0.000000001') <= amount <= Decimal(CAP) / NANO:
            raise ValueError('Invalid sample price')
        with localcontext() as context:
            context.prec = max(28, len(amount.as_tuple().digits) + 10)
            scaled = amount * NANO
            if scaled != scaled.to_integral_value():
                raise ValueError('Invalid sample price')
            return int(scaled)
    except (InvalidOperation, TypeError) as error:
        raise ValueError('Invalid sample price') from error


class PriceProvider(Protocol):
    source: str
    version: str
    valid_until: int | None

    def price(self, catalog_id: int) -> int: ...


class SamplePriceProvider:
    source = 'sample'
    valid_until = None

    def __init__(self, catalog):
        self._prices = {gift['id']: ton_to_nano(gift['price']) for gift in catalog}
        encoded = json.dumps(self._prices, sort_keys=True, separators=(',', ':')).encode()
        self.version = hashlib.sha256(encoded).hexdigest()

    def price(self, catalog_id: int) -> int:
        return self._prices[catalog_id]


def ask_price(base: int, markup_bps: int) -> int:
    # Round the seller's price upward to one nanoTON, without binary floats.
    return (base * (10_000 + markup_bps) + 9_999) // 10_000
