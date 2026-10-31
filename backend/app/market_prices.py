"""Optional display-only TON listing observations, never financial valuations."""
import json
import re
import time
from pathlib import Path

from .ledger import CAP

MARKET_PRICES_PATH = Path(__file__).resolve().parents[1] / 'data' / 'market-prices.json'
DAY = 86400


def _timestamp(value, now):
    return type(value) is int and 0 < value <= now + 60


def load_market_prices(known_pairs, path=None, now=None):
    """Return allowlisted metadata; discard an invalid snapshot as a whole.

    Expired observations remain available for stale labels. Unknown identity pairs
    are skipped, allowing a snapshot to cover a larger catalog than this instance.
    """
    now = int(time.time()) if now is None else now
    try:
        data = json.loads(Path(path if path is not None else MARKET_PRICES_PATH).read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1
                or data.get('source') != 'telegram-resale'
                or data.get('kind') != 'lowest_observed_listing'
                or type(data.get('complete')) is not bool
                or not isinstance(data.get('collections'), list)):
            return {}
        captured = data.get('capturedAt')
        until = data.get('validUntil')
        if (not _timestamp(captured, now) or type(until) is not int
                or not captured < until <= captured + DAY):
            return {}
        result = {}
        seen_telegram = set()
        seen_catalog = set()
        for entry in data['collections']:
            if not isinstance(entry, dict):
                return {}
            telegram_id, catalog_id = entry.get('telegramId'), entry.get('catalogId')
            checked, count = entry.get('checkedAt'), entry.get('sampleCount')
            status, floor = entry.get('status'), entry.get('floorNano')
            if (not isinstance(telegram_id, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', telegram_id)
                    or type(catalog_id) is not int or catalog_id < 100000
                    or telegram_id in seen_telegram or catalog_id in seen_catalog
                    or not _timestamp(checked, now)
                    or not checked < until <= checked + DAY
                    or type(count) is not int or count < 0
                    or type(entry.get('hasMore')) is not bool
                    or status not in ('available', 'no_ton_listings', 'not_collectible', 'error')):
                return {}
            inspected = entry.get('inspectedCount', count)
            if type(inspected) is not int or inspected < count:
                return {}
            if status == 'available':
                if (not isinstance(floor, str) or not re.fullmatch(r'[1-9][0-9]{0,14}', floor)
                        or int(floor) > CAP or count == 0):
                    return {}
            elif floor is not None:
                return {}
            seen_telegram.add(telegram_id)
            seen_catalog.add(catalog_id)
            if status == 'available' and (telegram_id, catalog_id) in known_pairs:
                result[catalog_id] = {
                    'floorNano': floor, 'checkedAt': checked, 'validUntil': until,
                    'source': data['source'], 'kind': data['kind'],
                    'sampleCount': count, 'hasMore': entry['hasMore'],
                }
        return result
    except (OSError, ValueError, TypeError, RecursionError):
        return {}
