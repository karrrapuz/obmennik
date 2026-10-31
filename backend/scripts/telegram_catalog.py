"""Local-only Telethon login and read-only catalog probe. Never imported by API."""
import argparse
import asyncio
import base64
import getpass
import io
import logging
import re
import sys
import time
import warnings
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
CREDENTIALS = BACKEND / '.env.telegram'
SESSION = BACKEND / '.local' / 'telegram' / 'catalog.session'
QR_PAGE = SESSION.parent / 'login-qr.html'

ERROR_MESSAGES = {
    'ApiIdInvalidError': 'Telegram rejected API ID/hash. Check the pair from my.telegram.org.',
    'ApiIdPublishedFloodError': 'Telegram restricted these application credentials. Do not retry repeatedly.',
    'PhoneNumberInvalidError': 'Telegram rejected the phone number. Use its international +country format.',
    'PhoneNumberBannedError': 'Telegram reports that this phone number is banned.',
    'PhoneNumberFloodError': 'Too many login-code requests. Wait before trying again.',
    'PhoneCodeInvalidError': 'The login code is incorrect. No automatic new code was requested.',
    'PhoneCodeExpiredError': 'The login code has expired. Restart login when ready.',
    'PasswordHashInvalidError': 'The Telegram 2FA password is incorrect.',
    'AuthRestartError': 'Telegram requested a fresh login. Restart once when ready.',
}


class LocalInputError(ValueError):
    pass


def safe_failure(error):
    if isinstance(error, LocalInputError):
        return str(error)
    if isinstance(error, (OSError, TimeoutError)):
        return 'Cannot reach Telegram. Check your network connection before retrying.'
    return ERROR_MESSAGES.get(type(error).__name__,
        'Telegram command failed unexpectedly. No new login attempt was started automatically.')


@dataclass(frozen=True, repr=False)
class Credentials:
    api_id: int
    api_hash: str


def load_credentials(path: Path) -> Credentials:
    if not path.is_file():
        raise ValueError('Local credentials file is missing.')
    values = dotenv_values(path, interpolate=False)
    api_id = (values.get('TELEGRAM_API_ID') or '').strip()
    api_hash = (values.get('TELEGRAM_API_HASH') or '').strip()
    if not re.fullmatch(r'[1-9][0-9]{0,9}', api_id) or int(api_id) > 2_147_483_647:
        raise ValueError('Fill TELEGRAM_API_ID in the local credentials file.')
    if not re.fullmatch(r'[a-fA-F0-9]{32}', api_hash):
        raise ValueError('Fill TELEGRAM_API_HASH in the local credentials file.')
    return Credentials(int(api_id), api_hash)


def write_qr_page(url, path=QR_PAGE):
    import qrcode
    buffer = io.BytesIO()
    qrcode.make(url).save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta http-equiv="refresh" content="2"><title>GiftMoney: Telegram QR</title>
<style>body{font:18px Arial,sans-serif;background:#131313;color:white;text-align:center;margin:40px auto;max-width:640px;padding:0 20px}img{display:block;width:400px;max-width:100%;height:auto;margin:24px auto}p{line-height:1.5;color:#ccc}</style>
<h1>Вход в локальный импортёр GiftMoney</h1>
<p>Telegram на телефоне → Настройки → Устройства → Подключить устройство.</p>
<img alt="QR для входа" src="data:image/png;base64,''' + encoded + '''">
<p>QR обновляется автоматически. Не отправляйте его другим людям.</p>
<p>После сканирования проверьте PowerShell: может потребоваться пароль 2FA.</p></html>''', encoding='utf-8')


def close_qr_page(path=QR_PAGE):
    path.unlink(missing_ok=True)


async def qr_sign_in(client, password_error, prompt, show_qr, clear_qr, duration=300):
    deadline = time.monotonic() + duration
    try:
        qr = await client.qr_login()
        while time.monotonic() < deadline:
            # Register the login-token listener before exposing the QR to the user.
            waiter = asyncio.create_task(qr.wait())
            await asyncio.sleep(0)
            try:
                show_qr(qr.url)
                await asyncio.wait_for(waiter, timeout=max(0.1, deadline - time.monotonic()))
                return
            except password_error:
                clear_qr()
                print('QR accepted. Enter your Telegram 2FA password here (hidden).', flush=True)
                await client.sign_in(password=prompt('Telegram 2FA password (hidden): '))
                return
            except TimeoutError:
                if time.monotonic() >= deadline:
                    break
                await qr.recreate()
            finally:
                if not waiter.done():
                    waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
        raise LocalInputError('QR login timed out. Restart when ready to scan.')
    finally:
        clear_qr()


def local_qr_display():
    opened = False
    def show(url):
        nonlocal opened
        write_qr_page(url)
        if not opened:
            opened = True
            print('QR opened locally. Scan with Telegram Settings > Devices > Link Desktop Device.', flush=True)
            if not webbrowser.open(QR_PAGE.as_uri()):
                print('Open backend/.local/telegram/login-qr.html in your browser.', flush=True)
    return show


async def run_client(client, command, password_error, catalog_request=None, prompt=None, phone_prompt=None,
                     show_qr=None, clear_qr=None):
    phone_prompt = phone_prompt or prompt or input
    prompt = prompt or getpass.getpass
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
        if not authorized:
            if command == 'qr-login':
                await qr_sign_in(client, password_error, prompt,
                                 show_qr or local_qr_display(), clear_qr or close_qr_page)
            elif command != 'login':
                print('Not signed in. Run the login command in your own terminal.')
                return 2
            else:
                phone = re.sub(r'[\s()\-]', '', phone_prompt('Phone (+country...; visible): ').strip())
                if not re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
                    raise LocalInputError('Phone is empty or invalid. Enter the full number starting with +country code.')
                sent = await client.send_code_request(phone)
                code = prompt('Telegram login code (hidden): ').strip()
                if not re.fullmatch(r'[0-9]{4,8}', code):
                    raise LocalInputError('Login code must contain 4-8 digits; the code input is hidden.')
                try:
                    await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
                except password_error:
                    password = prompt('Telegram 2FA password (hidden): ')
                    await client.sign_in(password=password)
        if command == 'qr-login':
            await client.set_receive_updates(False)
        me = await client.get_me()
        if me is None or me.bot:
            raise LocalInputError('A user account is required, not a bot account.')
        if command == 'preview':
            result = await client(catalog_request)
            print(f'Catalog probe succeeded: {len(result.gifts)} gift types returned.')
        else:
            print('Telegram user session is ready. No gifts or messages were changed.')
        return 0
    finally:
        await client.disconnect()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check-config', 'login', 'qr-login', 'status', 'preview'))
    args = parser.parse_args(argv)
    try:
        credentials = load_credentials(CREDENTIALS)
    except ValueError:
        print('Fill valid TELEGRAM_API_ID and TELEGRAM_API_HASH in the local credentials file.')
        return 2
    except OSError:
        print('Cannot read the local credentials file.')
        return 2
    if args.command == 'check-config':
        print('Local credentials format is valid. No network request was made.')
        return 0
    if args.command not in ('login', 'qr-login') and not SESSION.is_file():
        print('No local session. Run the login command in your own terminal.')
        return 2
    if args.command in ('login', 'qr-login') and not sys.stdin.isatty():
        print('Open login in your own interactive terminal; hidden input is required.')
        return 2
    try:
        from telethon import TelegramClient, functions
        from telethon.errors import FloodWaitError, SessionPasswordNeededError
    except ImportError:
        print('Install backend/requirements-telegram.txt into the local virtual environment.')
        return 2
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        SESSION.parent.mkdir(parents=True, exist_ok=True)
        client = TelegramClient(str(SESSION), credentials.api_id, credentials.api_hash,
            receive_updates=args.command == 'qr-login', request_retries=2, connection_retries=1, auto_reconnect=False,
            raise_last_call_error=True, timeout=15, flood_sleep_threshold=0,
            device_model='GiftMoney Local Catalog Reader')
        client.session.save_entities = False
        request = functions.payments.GetStarGiftsRequest(hash=0) if args.command == 'preview' else None
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return asyncio.run(run_client(client, args.command, SessionPasswordNeededError, request))
    except FloodWaitError as error:
        print(f'Telegram rate limit: wait at least {error.seconds} seconds before retrying.')
        return 2
    except (KeyboardInterrupt, EOFError):
        print('Cancelled. No automatic retry will be made.')
        return 2
    except Exception as error:
        # Telegram exceptions can include credentials, phone numbers or request details.
        print(safe_failure(error))
        return 2
    finally:
        logging.disable(previous_logging)


if __name__ == '__main__':
    raise SystemExit(main())
