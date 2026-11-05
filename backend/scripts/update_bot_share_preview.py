"""Update only the bot's public descriptions; preserve name and profile photo."""
import argparse
from pathlib import Path
import httpx
from dotenv import dotenv_values

SHORT = 'Обмен подарков и займы в GRAM. Откройте приложение, чтобы посмотреть подарок.'
DESCRIPTION = 'Посмотрите этот красивый подарок для обмена в нашем приложении. Выбирайте подарки, обменивайтесь и получайте GRAM под залог.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    assert len(SHORT) <= 120 and len(DESCRIPTION) <= 512
    if not args.apply:
        print(SHORT)
        print(DESCRIPTION)
        return
    token = dotenv_values(Path(__file__).resolve().parents[1] / '.env').get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('Bot token missing')
    with httpx.Client(timeout=20) as client:
        for method, key, value in [('setMyShortDescription', 'short_description', SHORT), ('setMyDescription', 'description', DESCRIPTION)]:
            try:
                result = client.post(f'https://api.telegram.org/bot{token}/{method}', json={key: value}).json()
            except (httpx.HTTPError, ValueError):
                raise SystemExit('Telegram response uncertain; verify descriptions before retrying.') from None
            if result.get('ok') is not True:
                raise SystemExit(f'Telegram rejected description update: {result.get("error_code")}')
            print(f'{method}: updated')


if __name__ == '__main__':
    main()
