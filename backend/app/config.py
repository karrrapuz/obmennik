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
    trade_markup_bps: int = 500
    trade_quote_ttl: int = 120
    referral_rate_bps: int = 200
    telegram_bot_username: str = ''
    market_ingest_key: str = ''
    deployment_mode: str = 'demo'
    admin_user_ids: tuple[int, ...] = ()
    showcase_mode: bool = False

    def __post_init__(self):
        if self.deployment_mode not in {'demo', 'production'}:
            raise ValueError('DEPLOYMENT_MODE must be demo or production')
        if self.deployment_mode == 'production' and self.gift_provider_mode != 'disabled':
            raise ValueError('Production requires disabled gift custody until a live adapter is implemented')
        if any(type(value) is not int or not 0 < value < 2**63 for value in self.admin_user_ids):
            raise ValueError('ADMIN_USER_IDS must contain positive Telegram user IDs')
        if type(self.showcase_mode) is not bool:
            raise ValueError('SHOWCASE_MODE must be a boolean')

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
        try:
            markup = int(os.getenv('TRADE_MARKUP_BPS', '500'))
            ttl = int(os.getenv('TRADE_QUOTE_TTL', '120'))
            referral_rate = int(os.getenv('REFERRAL_RATE_BPS', '200'))
        except ValueError:
            raise RuntimeError('Trade pricing configuration must use integers') from None
        raw_admins = os.getenv('ADMIN_USER_IDS', '').strip()
        showcase = os.getenv('SHOWCASE_MODE', 'false').strip()
        if showcase not in {'true', 'false'}:
            raise RuntimeError('SHOWCASE_MODE must be true or false')
        parts = raw_admins.split(',') if raw_admins else []
        if (len(parts) > 20 or any(not part.strip().isascii() or not part.strip().isdecimal()
                                  or len(part.strip()) > 19 for part in parts)):
            raise RuntimeError('ADMIN_USER_IDS must be a comma-separated list of numeric Telegram user IDs')
        return cls(token, url, tuple(x.strip() for x in os.getenv(
            'ALLOWED_ORIGINS', 'http://localhost:5173,https://obmennik-kappa.vercel.app'
        ).split(',') if x.strip()), gift_provider_mode=os.getenv('GIFT_PROVIDER_MODE', 'demo').strip(),
            trade_markup_bps=markup, trade_quote_ttl=ttl, referral_rate_bps=referral_rate,
            telegram_bot_username=os.getenv('TELEGRAM_BOT_USERNAME', '').strip().lstrip('@'),
            market_ingest_key=os.getenv('MARKET_INGEST_KEY', '').strip(),
            deployment_mode=os.getenv('DEPLOYMENT_MODE', 'demo').strip(),
            admin_user_ids=tuple(dict.fromkeys(int(part.strip()) for part in parts)),
            showcase_mode=showcase == 'true')
