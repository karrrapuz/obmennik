"""Create a PostgreSQL custom-format backup. No scheduler or cloud upload."""
import argparse
import os
import re
from pathlib import Path
import subprocess

from sqlalchemy.engine import make_url


def backup_database(database_url, output, *, timeout=3600):
    url = make_url(database_url)
    allowed = {'sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'channel_binding'}
    if (url.get_backend_name() != 'postgresql' or not url.host or not url.database
            or not re.fullmatch(r'[A-Za-z0-9_.-]+', url.database)
            or set(url.query) - allowed
            or any(not isinstance(value, str) for value in url.query.values())
            or url.query.get('sslmode', 'verify-full') not in ('require', 'verify-ca', 'verify-full')):
        raise ValueError('A PostgreSQL URL with supported TLS options is required')
    # libpq receives connection fields separately, never a connection URI in argv.
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith('PG') and key.upper() != 'DATABASE_URL'}
    env.update(PGHOST=url.host, PGPORT=str(url.port or 5432), PGDATABASE=url.database,
               PGUSER=url.username or '', PGPASSWORD=url.password or '', PGCONNECT_TIMEOUT='15',
               PGSSLMODE='verify-full')
    env.update({f'PG{key.upper()}': value for key, value in url.query.items()})
    path = Path(output).expanduser().resolve()
    repository = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repository):
        raise ValueError('Database archives must be stored outside the repository')
    created = False
    try:
        # Exclusive creation protects existing backups, including symlink targets.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            subprocess.run(['pg_dump', '--format=custom', '--no-password'], stdout=stream,
                           stderr=subprocess.DEVNULL, env=env, check=True, timeout=timeout)
        if path.stat().st_size == 0:
            raise RuntimeError('Empty backup')
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New archive path outside the repository')
    args = parser.parse_args()
    try:
        backup_database(os.environ.get('DATABASE_URL', ''), args.output)
    except Exception:
        print('Backup failed; check connection, pg_dump version, permissions and output path. Details withheld.')
        return 1
    print('Backup created. Verify in an isolated database; this archive contains sensitive data.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
