import importlib.util
from pathlib import Path

import pytest

from test_auth import settings

spec = importlib.util.spec_from_file_location('smoke_api_script', Path(__file__).resolve().parents[1] / 'scripts/smoke_api.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:secret@example.com',
                                'https://example.com/api', 'https://example.com?token=secret',
                                'https://example.com#secret', 'ftp://example.com'])
def test_probe_rejects_unsafe_origins(url):
    with pytest.raises(ValueError):
        smoke.probe(url)


@pytest.mark.parametrize('iterations,concurrency', [(0, 1), (21, 1), (1, 0), (1, 6)])
def test_probe_is_bounded(iterations, concurrency):
    with pytest.raises(ValueError):
        smoke.probe('https://example.com', iterations, concurrency)


def test_freshness_and_expiry():
    feed = {'capturedAt': 1000, 'validUntil': 2000, 'collections': [{}], 'complete': True}
    assert smoke.fresh_feed(feed, 1500)
    assert not smoke.fresh_feed(feed, 2000)
    for patch in ({'complete': False}, {'collections': []}, {'capturedAt': True},
                  {'capturedAt': 1561}, {'validUntil': 100000}):
        assert not smoke.fresh_feed({**feed, **patch}, 1500)
