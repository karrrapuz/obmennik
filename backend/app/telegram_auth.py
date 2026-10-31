import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TelegramUser(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int = Field(gt=0, le=2**52 - 1)
    first_name: str = Field(min_length=1, max_length=256)
    last_name: str | None = Field(default=None, max_length=256)
    username: str | None = Field(default=None, max_length=64)
    photo_url: str | None = Field(default=None, max_length=2048)


class InvalidInitData(ValueError):
    pass


def validate_init_data(raw: str, token: str, max_age: int, *, include_start_param=False):
    try:
        if not raw or len(raw) > 16384 or re.search(r'%(?![0-9a-fA-F]{2})', raw):
            raise ValueError()
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          encoding='utf-8', errors='strict', max_num_fields=30)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError()
        received_hash = fields.pop('hash')
        if not re.fullmatch('[0-9a-fA-F]{64}', received_hash):
            raise ValueError()
        check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
        secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash.lower()):
            raise ValueError()
        auth_date = int(fields['auth_date'])
        now = int(time.time())
        if auth_date > now + 30 or now - auth_date > max_age:
            raise ValueError()
        user = TelegramUser.model_validate(json.loads(fields['user']))
        # Only Telegram's HTTPS photo URLs are rendered; no arbitrary schemes.
        if user.photo_url and not user.photo_url.startswith('https://'):
            user.photo_url = None
        if include_start_param:
            return user, expected, auth_date, fields.get('start_param', '')
        return user, expected, auth_date
    except (ValueError, KeyError, TypeError, ValidationError, UnicodeError):
        raise InvalidInitData('Invalid or expired Telegram data') from None
