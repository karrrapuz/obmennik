"""Read-only token check. Never prints the token or full request URL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import Settings

try:
    settings = Settings.from_env()
    response = httpx.get(f'https://api.telegram.org/bot{settings.bot_token}/getMe', timeout=15)
    data = response.json()
    if not data.get('ok'):
        print('Bot token check failed; check token in backend/.env')
        sys.exit(1)
    print('Bot token valid. Bot username: @' + data['result']['username'])
except Exception:
    print('Bot verification unavailable; no secret details logged')
    sys.exit(1)
