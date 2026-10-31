"""Optional descriptive names for Telegram types without an official title."""
import json
import re
from pathlib import Path

LABELS_PATH = Path(__file__).resolve().parents[1] / 'data/catalog-labels.json'


def load_labels(path=None):
    try:
        data = json.loads(Path(path or LABELS_PATH).read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1
                or not isinstance(data.get('labels'), list) or len(data['labels']) > 1000):
            return {}
        result = {}
        for item in data['labels']:
            identity, title = item.get('telegramId'), item.get('displayTitle')
            if (not isinstance(identity, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', identity)
                    or identity in result or not isinstance(title, str) or not title.strip()
                    or len(title) > 120 or any(ord(c) < 32 for c in title)
                    or item.get('kind') != 'descriptive'):
                return {}
            result[identity] = title.strip()
        return result
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return {}


def resolve_title(collection, labels):
    official = collection.get('sourceTitle')
    if isinstance(official, str) and official.strip():
        return official.strip(), 'official'
    if collection['telegramId'] in labels:
        return labels[collection['telegramId']], 'descriptive'
    return collection['title'], 'unavailable' if 'sourceTitle' in collection else 'official'
