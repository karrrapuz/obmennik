"""Restrict local SQLite session storage before Telethon opens it."""

import os
from pathlib import Path


def protect_session_storage(session: Path) -> None:
    # CLI entrypoints own the process; keep the mask for SQLite sidecars and QR files.
    if os.name == "posix":
        os.umask(0o077)
    session.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "posix":
        return  # Windows ACLs, not chmod, control access.
    if session.parent.is_symlink():
        raise ValueError("Telegram session directory must not be a symlink")
    session.parent.chmod(0o700)
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = session.with_name(session.name + suffix)
        if path.is_symlink():
            raise ValueError("Telegram session file must not be a symlink")
        if path.exists():
            if not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError("Telegram session must be a regular private file")
            path.chmod(0o600)
