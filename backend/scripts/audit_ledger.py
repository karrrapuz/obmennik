"""Run from the repository root: python backend/scripts/audit_ledger.py."""
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ledger_audit import audit_ledger


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    url = os.getenv('DATABASE_URL', '').strip()
    if not url:
        print('DATABASE_URL is required', file=sys.stderr)
        return 2
    if url.startswith(('postgres://', 'postgresql://')):
        url = 'postgresql+psycopg://' + url.split('://', 1)[1]
    engine = None
    try:
        engine = create_engine(url)
        with engine.connect() as connection:
            report = audit_ledger(connection)
        print(json.dumps(report, sort_keys=True))
        return 0 if report['ok'] else 1
    except Exception:
        print('Ledger audit failed; check database connectivity and schema.', file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
