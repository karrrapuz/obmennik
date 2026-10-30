"""Apply tracked migrations to the explicitly configured staging database."""
import sys
from pathlib import Path
from dotenv import load_dotenv
from alembic import command
from alembic.config import Config

root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env.neon', override=True)
sys.path.insert(0, str(root))
try:
    command.upgrade(Config(str(root / 'alembic.ini')), 'head')
    print('Staging database migration: OK')
except Exception:
    print('Staging database migration failed; connection details not logged')
    sys.exit(1)
