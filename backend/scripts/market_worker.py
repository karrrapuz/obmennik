"""Opt-in dedicated-account market worker. Never logs in or reads local secrets."""
import argparse
import asyncio
import logging
import os
import re
import signal
import struct
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from scripts import telegram_prices as collector


class WorkerConfigurationError(ValueError):
    pass


class AuthorizationRequired(RuntimeError):
    pass


@dataclass(frozen=True, repr=False)
class WorkerSettings:
    api_id: int
    api_hash: str
    session_string: str
    push_configuration: tuple[str, str]
    work_dir: Path
    interval: int
    pages: int
    cycle_timeout: int
    max_failures: int

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        if (env.get('MARKET_WORKER_ENABLED') != 'true'
                or env.get('MARKET_ALLOW_CLOUD_SESSION') != 'true'
                or env.get('MARKET_SESSION_ACCOUNT') != 'dedicated'):
            raise WorkerConfigurationError('Dedicated-account worker is disabled; explicit approval required')

        def integer(name, default, low, high):
            raw = env.get(name, str(default))
            if not re.fullmatch(r'[1-9][0-9]{0,9}', raw) or not low <= int(raw) <= high:
                raise WorkerConfigurationError('Invalid worker numeric configuration')
            return int(raw)

        api_id = integer('TELEGRAM_API_ID', 0, 1, 2_147_483_647)
        api_hash = env.get('TELEGRAM_API_HASH', '')
        session_string = env.get('TELEGRAM_SESSION_STRING', '')
        if not re.fullmatch(r'[a-fA-F0-9]{32}', api_hash):
            raise WorkerConfigurationError('Dedicated Telegram API credentials required')
        if not re.fullmatch(r'1[A-Za-z0-9_=-]{100,511}', session_string):
            raise WorkerConfigurationError('Dedicated StringSession secret required')
        try:
            # Validate the in-memory auth key before opening any network connection.
            from telethon.sessions import StringSession
            if StringSession(session_string).auth_key is None:
                raise ValueError()
            push = collector.validate_push_configuration(env.get('MARKET_API_URL', ''),
                                                          env.get('MARKET_INGEST_KEY', ''))
        except (ValueError, TypeError, OSError, struct.error):
            raise WorkerConfigurationError('Invalid worker session or HTTPS ingest configuration') from None
        work_dir = Path(env.get('MARKET_WORK_DIR', str(Path(tempfile.gettempdir()) / 'giftmoney-market-worker')))
        if not work_dir.is_absolute() or '..' in work_dir.parts:
            raise WorkerConfigurationError('MARKET_WORK_DIR must be an absolute spool directory')
        return cls(api_id, api_hash, session_string, push, work_dir,
            integer('MARKET_INTERVAL_SECONDS', 3600, 3600, 86400),
            integer('MARKET_PAGES', 2, 1, 3),
            integer('MARKET_CYCLE_TIMEOUT_SECONDS', 1800, 60, 3600),
            integer('MARKET_MAX_FAILURES', 3, 1, 10))


@contextmanager
def spool_lock(directory):
    """OS-released lock prevents overlap on one host/shared spool, including crashes."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'worker.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
        handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise WorkerConfigurationError('Another worker owns this spool directory') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def make_client(settings):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(settings.session_string), settings.api_id, settings.api_hash,
        receive_updates=False, request_retries=1, connection_retries=1, auto_reconnect=False,
        flood_sleep_threshold=0, raise_last_call_error=True, timeout=20,
        device_model='GiftMoney Dedicated Market Worker')
    client.session.save_entities = False
    return client


@contextmanager
def spool_paths(directory):
    names = ('OUTPUT', 'PUBLIC', 'CHECKPOINT', 'LISTINGS')
    previous = {name: getattr(collector, name) for name in names}
    filenames = ('market-prices.json', 'public-prices.json', 'prices-progress.json', 'market-listings.json')
    try:
        for name, filename in zip(names, filenames):
            setattr(collector, name, directory / filename)
        yield
    finally:
        for name, path in previous.items():
            setattr(collector, name, path)


async def collect_and_push(settings, stop, client_factory=make_client, push=None):
    client = client_factory(settings)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise AuthorizationRequired('Dedicated session is unauthorized; no login attempted')
        feed = await collector.collect(client, pages=settings.pages, listings=True)
    finally:
        async with asyncio.timeout(10):
            await client.disconnect()
    if stop.is_set():
        return
    if not feed['complete']:
        raise RuntimeError('Incomplete public collection; no upload attempted')
    await (collector.push_snapshot if push is None else push)(feed, settings.push_configuration)


async def run_worker(settings, stop=None, *, once=False, client_factory=make_client, push=None):
    """No overlapping cycles; one bounded attempt per interval, then fail closed."""
    from telethon.errors import FloodWaitError
    stop = asyncio.Event() if stop is None else stop
    failures = 0
    with spool_lock(settings.work_dir), spool_paths(settings.work_dir):
        while not stop.is_set():
            delay = settings.interval

            async def cycle():
                async with asyncio.timeout(settings.cycle_timeout):
                    await collect_and_push(settings, stop, client_factory, push)

            job = asyncio.create_task(cycle())
            stopped = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait((job, stopped), return_when=asyncio.FIRST_COMPLETED)
                if stop.is_set():
                    job.cancel()
                    await asyncio.gather(job, return_exceptions=True)
                    return 0
                await job
                failures = 0
                print('Market worker cycle uploaded a complete public snapshot.', flush=True)
            except AuthorizationRequired:
                print('Market worker authorization required; stopped without login.', flush=True)
                return 2
            except Exception as error:
                failures += 1
                if isinstance(error, FloodWaitError):
                    delay = max(delay, error.seconds + 1)
                print(f'Market worker cycle failed ({type(error).__name__}); private details omitted.', flush=True)
                if once or failures >= settings.max_failures:
                    return 2
            finally:
                stopped.cancel()
                if not job.done():
                    job.cancel()
                await asyncio.gather(job, stopped, return_exceptions=True)
            if once:
                return 0
            print(f'Market worker waiting {delay}s before the next bounded attempt.', flush=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass
    return 0


async def serve(settings, once=False):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
            installed.append(sig)
        except (NotImplementedError, RuntimeError):
            # Linux container is the production target; Windows retains Ctrl+C cancellation.
            pass
    try:
        return await run_worker(settings, stop, once=once)
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='One bounded collect/upload attempt, then exit')
    parser.add_argument('--check-config', action='store_true', help='Validate environment only; no files or network')
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    os.umask(0o077)
    try:
        settings = WorkerSettings.from_env()
        if args.check_config:
            print('Dedicated market worker configuration is valid; activation not performed.', flush=True)
            return 0
        return asyncio.run(serve(settings, args.once))
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f'Market worker stopped ({type(error).__name__}); configuration/private details omitted.', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
