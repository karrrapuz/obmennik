"""Explicitly backfill the simulated featured gift; never transfer Telegram assets."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.config import Settings
from app.models import User
from app.gift_provider import create_gift_provider
from app.inventory import ensure_inventory
from app.inventory_models import InventoryGift
from app.ledger import lock_user


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('Dry run: use --apply to grant one simulated gift per account.')
        return
    settings = Settings.from_env()
    if settings.deployment_mode != 'demo' or settings.gift_provider_mode != 'demo':
        raise SystemExit('Test grants are forbidden outside demo mode.')
    url = dotenv_values(Path(__file__).resolve().parents[1] / '.env.neon').get('DATABASE_URL')
    if not url:
        raise SystemExit('Explicit staging database connection is missing.')
    url = url.replace('postgres://', 'postgresql+psycopg://', 1).replace('postgresql://', 'postgresql+psycopg://', 1)
    engine = create_engine(url)
    provider = create_gift_provider('demo', showcase=True)
    with Session(engine) as db:
        if db.scalar(text('SELECT version_num FROM alembic_version')) != '0009_shared_gifts':
            raise SystemExit('Deploy the current schema before applying test grants.')
        users = db.scalars(select(User.id).order_by(User.id)).all()
    granted = 0
    for user_id in users:
        with Session(engine) as db:
            lock_user(db, user_id)
            before = db.scalar(select(InventoryGift.id).where(InventoryGift.user_id == user_id, InventoryGift.catalog_id == 90001))
            ensure_inventory(db, user_id, provider)
            after = db.scalar(select(InventoryGift.id).where(InventoryGift.user_id == user_id, InventoryGift.catalog_id == 90001))
            granted += int(before is None and after is not None)
            db.commit()
    engine.dispose()
    print(f'Accounts checked: {len(users)}; simulated gifts added: {granted}. No Telegram transfers or balance changes.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Grant stopped:', type(error).__name__)
        raise SystemExit(1)
