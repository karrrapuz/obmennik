import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    allowed_origins: tuple[str, ...]
    init_data_max_age: int = 300
    session_ttl: int = 86400
    gift_provider_mode: str = 'demo'

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / '.env')
        token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
        if not token:
            raise RuntimeError('TELEGRAM_BOT_TOKEN is required')
        url = os.getenv('DATABASE_URL', 'sqlite:///./giftmoney.db')
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        return cls(token, url, tuple(x.strip() for x in os.getenv(
            'ALLOWED_ORIGINS', 'http://localhost:5173,https://obmennik-kappa.vercel.app'
        ).split(',') if x.strip()), gift_provider_mode=os.getenv('GIFT_PROVIDER_MODE', 'demo').strip())
