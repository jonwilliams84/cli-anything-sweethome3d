"""Timestamped backups of .sh3d (or any) files before in-place edits.

Pattern:
    from cli_anything.sweethome3d.core.backup import backup, restore_latest
    backup(path)             # before mutating
    ...do the edit...
    # if you regret it:
    restore_latest(path)

Backups live in a sibling ``<stem>.backups/`` folder so they don't pollute
the parent directory. Each backup is named
``<original-stem>.<UTC-timestamp>.<ext>`` — sortable by name.

`backup()` keeps the most recent ``KEEP`` files (default 20) and prunes
older ones automatically; no manual cleanup needed.
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from typing import Optional

KEEP_LAST = 20


def _backup_dir(path: Path) -> Path:
    return path.with_name(path.stem + ".backups")


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(path: str | Path, *, keep: int = KEEP_LAST) -> Path:
    """Snapshot ``path`` to ``<path>.backups/<stem>.<timestamp>.<ext>``.

    Returns the backup path. Prunes older backups beyond ``keep``.
    No-op if the source doesn't exist.
    """
    p = Path(path)
    if not p.exists():
        return p
    bd = _backup_dir(p)
    bd.mkdir(parents=True, exist_ok=True)
    dst = bd / f"{p.stem}.{_stamp()}{p.suffix}"
    shutil.copy2(p, dst)
    # Prune
    snaps = sorted(bd.glob(f"{p.stem}.*{p.suffix}"))
    for old in snaps[:-keep]:
        old.unlink()
    return dst


def list_backups(path: str | Path) -> list[Path]:
    """Return existing backups for ``path`` sorted newest-last."""
    p = Path(path)
    bd = _backup_dir(p)
    if not bd.exists():
        return []
    return sorted(bd.glob(f"{p.stem}.*{p.suffix}"))


def restore_latest(path: str | Path) -> Optional[Path]:
    """Restore the most recent backup over ``path``. Returns the snapshot
    that was restored, or ``None`` if no backups exist."""
    p = Path(path)
    snaps = list_backups(p)
    if not snaps:
        return None
    latest = snaps[-1]
    # Take a fresh backup of the CURRENT state first so undo is itself
    # reversible (poor-man's redo).
    backup(p)
    shutil.copy2(latest, p)
    return latest


def restore_at(path: str | Path, snapshot: str | Path) -> Path:
    """Restore a specific snapshot by name (or absolute path)."""
    p = Path(path)
    snap = Path(snapshot)
    if not snap.is_absolute():
        snap = _backup_dir(p) / snap
    if not snap.exists():
        raise FileNotFoundError(f"snapshot not found: {snap}")
    backup(p)
    shutil.copy2(snap, p)
    return snap
