"""Bounded read-only availability probe. No login, writes or secrets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import time
from urllib.parse import urlsplit

import httpx


def fresh_feed(body, now):
    captured, until = body.get('capturedAt'), body.get('validUntil')
    return (body.get('complete') is True and isinstance(body.get('collections'), list)
            and bool(body['collections']) and type(captured) is int and type(until) is int
            and 0 < captured <= now + 60 and now < until <= captured + 86400)


def probe(base, iterations=3, concurrency=2, require_fresh=False):
    parsed = urlsplit(base)
    if (parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}
            or (parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1'})):
        raise ValueError('An HTTPS API origin (or local HTTP origin) is required')
    if not 1 <= iterations <= 20 or not 1 <= concurrency <= 5:
        raise ValueError('Probe limits: 1..20 iterations, 1..5 concurrent requests')
    paths = ['/api/health', '/api/market/prices'] * iterations
    with httpx.Client(base_url=base.rstrip('/'), timeout=30, follow_redirects=False, trust_env=False) as client:
        # Free staging hosts may cold-start. Warm once, with a finite deadline;
        # measured requests below do not hide failures behind automatic retries.
        try:
            warm = client.get('/api/health', timeout=90)
            if warm.status_code != 200 or warm.json().get('status') != 'ok':
                raise ValueError('Health check failed')
        except (httpx.HTTPError, ValueError, AttributeError):
            return {'ok': False, 'requests': 1, 'failures': 1, 'warmup_failed': True,
                    'scope': 'read_only_smoke_not_capacity_certification'}
        def request(path):
            started = time.monotonic()
            try:
                response = client.get(path)
                body = response.json()
                valid = response.status_code == 200 and (
                    body.get('status') == 'ok' if path.endswith('health') else
                    isinstance(body.get('collections'), list) and body.get('source') == 'telegram-resale')
                if valid and path.endswith('prices') and require_fresh:
                    valid = fresh_feed(body, time.time())
            except (httpx.HTTPError, ValueError, AttributeError):
                valid = False
            return {'ok': valid, 'milliseconds': round((time.monotonic() - started) * 1000)}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(request, paths))
    latencies = sorted(item['milliseconds'] for item in results)
    return {'ok': all(item['ok'] for item in results), 'requests': len(results) + 1,
            'failures': sum(not item['ok'] for item in results),
            'p95_ms': latencies[min(len(latencies) - 1, int(len(latencies) * .95))],
            'scope': 'read_only_smoke_not_capacity_certification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--iterations', type=int, default=3)
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--require-fresh', action='store_true', help='Fail on missing/incomplete/expired market snapshots')
    args = parser.parse_args()
    try:
        result = probe(args.url, args.iterations, args.concurrency, args.require_fresh)
    except Exception:
        print('Probe configuration or execution failed', file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
