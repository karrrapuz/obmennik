"""Local gift-provider contract. No Telegram custody or external delivery."""
import json
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException


class GiftProvider(Protocol):
    mode: str
    catalog: tuple[dict, ...]

    def require_available(self) -> None: ...
    def initial_gifts(self) -> tuple[tuple[int, bool], ...]: ...
    def deposit_catalog_id(self) -> int: ...
    def status(self) -> dict: ...


class StubGiftProvider:
    def __init__(self, mode: str):
        if mode not in {'demo', 'disabled'}:
            raise ValueError('GIFT_PROVIDER_MODE must be demo or disabled; live delivery is not implemented')
        self.mode = mode
        path = Path(__file__).resolve().parents[1] / 'data/catalog-sample.json'
        self.catalog = tuple(json.loads(path.read_text(encoding='utf-8')))

    def require_available(self) -> None:
        if self.mode != 'demo':
            raise HTTPException(503, 'Gift provider is not configured')

    def initial_gifts(self) -> tuple[tuple[int, bool], ...]:
        if self.mode != 'demo':
            return ()
        return tuple((gift['id'], index < 3) for index, gift in enumerate(self.catalog[:5]))

    def deposit_catalog_id(self) -> int:
        self.require_available()
        return self.catalog[1]['id']

    def status(self) -> dict:
        return {'mode': self.mode, 'available': self.mode == 'demo',
                'simulated': True, 'real_transfers': False}


def create_gift_provider(mode: str) -> GiftProvider:
    return StubGiftProvider(mode)
