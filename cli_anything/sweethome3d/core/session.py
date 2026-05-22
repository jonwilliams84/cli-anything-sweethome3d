"""Stateful session — load a `.sh3d` file, mutate it, save it.

Adds undo/redo via XML snapshots: every mutation pushes the previous XML to
an undo stack; `undo()` restores it. Snapshots are kept in memory only.

Session save uses the locked-write pattern (write `.tmp`, then atomic rename)
to prevent corruption on concurrent saves.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Optional

from cli_anything.sweethome3d.core.model import Home
from cli_anything.sweethome3d.core.project import (
    new_home,
    open_home,
    save_home,
)


MAX_UNDO_DEPTH = 50


class Session:
    """Stateful container for an open Sweet Home 3D project."""

    def __init__(self, home: Home, path: Optional[str] = None):
        self.home: Home = home
        self.path: Optional[str] = path
        self._modified: bool = False
        self._undo_stack: list[Home] = []
        self._redo_stack: list[Home] = []
        # The file we copy embedded content from on save (textures, models).
        # Updated each time we open or save to a real file.
        self._content_source: Optional[str] = path
        # Bytes to embed on the next save (e.g. background-image PNGs).
        # Cleared after the bytes land in the saved .sh3d.
        self._pending_content: dict[str, bytes] = {}

    def add_content(self, entry_name: str, data: bytes) -> None:
        """Queue a binary ZIP entry to be embedded on the next save.

        Used by commands that attach external assets (background images,
        custom textures) so the bytes land alongside `Home.xml` in the
        target .sh3d.
        """
        self._pending_content[entry_name] = data
        self._modified = True

    # ── lifecycle ──────────────────────────────────────────────────────────

    @classmethod
    def open(cls, path: str) -> "Session":
        home = open_home(path)
        return cls(home, path)

    @classmethod
    def new(cls, name: Optional[str] = None) -> "Session":
        return cls(new_home(name))

    def close(self) -> None:
        self.home = None  # type: ignore[assignment]
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ── persistence ────────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        """Save the session. If `path` is None, requires a previously-set path."""
        target = path or self.path
        if not target:
            raise ValueError("no path: call save(path) the first time")
        save_home(self.home, target,
                   copy_content_from=self._content_source,
                   extra_content=self._pending_content or None)
        self.path = target
        self._content_source = target
        self._pending_content = {}
        self._modified = False
        return target

    # ── undo/redo ──────────────────────────────────────────────────────────

    def checkpoint(self) -> None:
        """Snapshot the current home onto the undo stack."""
        self._undo_stack.append(deepcopy(self.home))
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._modified = True

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(deepcopy(self.home))
        self.home = self._undo_stack.pop()
        self._modified = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(deepcopy(self.home))
        self.home = self._redo_stack.pop()
        self._modified = True
        return True

    # ── status ─────────────────────────────────────────────────────────────

    @property
    def modified(self) -> bool:
        return self._modified

    def status(self) -> dict:
        return {
            "path": self.path,
            "name": self.home.name if self.home else None,
            "modified": self._modified,
            "undo_depth": len(self._undo_stack),
            "redo_depth": len(self._redo_stack),
            "objects": {
                "walls": len(self.home.walls) if self.home else 0,
                "rooms": len(self.home.rooms) if self.home else 0,
                "furniture": len(self.home.furniture) if self.home else 0,
                "levels": len(self.home.levels) if self.home else 0,
            },
        }
