"""
modify_rooms.py — Python wrapper for the ModifyRooms Java CLI tool.

Compiles ModifyRooms.java on first call (lazy, per-process, mirrors the
pattern used in render_runtime.py for Render.java / GpuRender.java / ExportObj.java),
then runs it with the given JSON spec.

Public API
----------
  modify_rooms(home_path, spec, *, out_path=None) -> dict
      Apply per-room edits to a SweetHome3D .sh3d file.

      Parameters
      ----------
      home_path : str
          Path to the source .sh3d file.
      spec : dict
          Room-edit specification (see ModifyRooms.java for the JSON schema).
          Keys: "rooms" (list of room-edit dicts, each with "id" or "match"
          plus optional floor/ceiling/wall_sides/baseboard fields).
      out_path : str or None
          Destination .sh3d path.  If None, the source file is overwritten
          in-place (a temporary file is used as staging to prevent corruption).

      Returns
      -------
      dict with keys:
          rooms_modified : int
          output         : str  (absolute path to the written file)
          elapsed_s      : float
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Per-process compile state (mirrors render_runtime.py pattern)
# ---------------------------------------------------------------------------
_modify_compiled: bool = False
_modify_classes_dir: Optional[Path] = None


# ---------------------------------------------------------------------------
# Path helpers (reuse logic from render_runtime; imported lazily to avoid
# circular imports)
# ---------------------------------------------------------------------------

def _sh3d_home() -> Path:
    """Return the SweetHome3D installation directory."""
    from cli_anything.sweethome3d.core.render_runtime import _find_sh3d_home
    return _find_sh3d_home()


def _javac_bin() -> Path:
    """Return path to a javac binary."""
    from cli_anything.sweethome3d.core.render_runtime import _find_javac
    return _find_javac()


def _java_bin(sh3d_home: Path) -> Path:
    """Return the SH3D-bundled java binary."""
    java = sh3d_home / "runtime" / "bin" / "java"
    if not java.exists():
        raise RuntimeError(f"SH3D bundled java not found at {java}")
    return java


def _sources_dir() -> Path:
    """Directory that contains ModifyRooms.java (the render/ package)."""
    return Path(__file__).parent.parent / "render"


def _cache_dir() -> Path:
    """XDG cache dir for compiled classes."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "cli-anything-sweethome3d" / "render"


def _build_classpath(sh3d_home: Path, classes_dir: Path) -> str:
    """Colon-separated classpath: all SH3D jars + compiled classes dir."""
    jars = sorted(glob.glob(str(sh3d_home / "lib" / "*.jar")))
    if not jars:
        raise RuntimeError(f"No .jar files under {sh3d_home / 'lib'}")
    return ":".join(jars + [str(classes_dir)])


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def _needs_compile(src: Path, cls: Path) -> bool:
    if not cls.exists():
        return True
    return src.stat().st_mtime > cls.stat().st_mtime


def _ensure_compiled() -> tuple[Path, Path]:
    """Compile ModifyRooms.java if stale; return (sh3d_home, classes_dir)."""
    global _modify_compiled, _modify_classes_dir

    sh3d_home = _sh3d_home()
    if _modify_classes_dir is None:
        _modify_classes_dir = _cache_dir()

    if _modify_compiled:
        return sh3d_home, _modify_classes_dir

    src = _sources_dir() / "ModifyRooms.java"
    if not src.exists():
        raise RuntimeError(
            f"ModifyRooms.java not found at {src}.\n"
            "Ensure the render/ package was installed correctly."
        )

    cls = _modify_classes_dir / "ModifyRooms.class"
    if not _needs_compile(src, cls):
        _modify_compiled = True
        return sh3d_home, _modify_classes_dir

    # Need to compile
    _modify_classes_dir.mkdir(parents=True, exist_ok=True)
    jars = sorted(glob.glob(str(sh3d_home / "lib" / "*.jar")))
    cp = ":".join(jars)
    javac = _javac_bin()

    cmd = [
        str(javac),
        "-source", "8", "-target", "8",
        "-cp", cp,
        "-d", str(_modify_classes_dir),
        str(src),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"javac failed compiling ModifyRooms.java (exit {result.returncode}):\n"
            f"  command: {' '.join(cmd)}\n"
            f"  stdout: {result.stdout.strip()}\n"
            f"  stderr: {result.stderr.strip()}"
        )

    _modify_compiled = True
    return sh3d_home, _modify_classes_dir


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def modify_rooms(
    home_path: str,
    spec: dict,
    *,
    out_path: Optional[str] = None,
    timeout: int = 120,
) -> dict:
    """Apply per-room edits to a SweetHome3D .sh3d file via ModifyRooms.java.

    Parameters
    ----------
    home_path : str
        Path to the source .sh3d file.
    spec : dict
        Room-edit specification.  Example::

            {
              "rooms": [
                {
                  "id": "room-c86e0c29-...",
                  "floor_color": "FFD8C6A4",
                  "floor_visible": True,
                  "wall_sides_color": "FFFFC0CB",
                  "baseboard": {"color": "FFFFFFFF", "height_cm": 10.0}
                },
                {
                  "match": {"level": "Level 0", "min_area_cm2": 50000},
                  "floor_color": "FF9C7A4D"
                }
              ]
            }

        Each room entry must have either ``"id"`` (exact room UUID) or
        ``"match"`` (predicate dict with optional ``"level"``, ``"min_area_cm2"``,
        ``"max_area_cm2"`` fields).

        Colour strings are 8-char ARGB hex (e.g. ``"FFD8C6A4"``) or 6-char
        RGB hex; the alpha byte is stripped before passing to SH3D.

    out_path : str or None
        Destination path.  If ``None``, the source file is overwritten in-place
        using a safe tmp→rename strategy.

    timeout : int
        Subprocess timeout in seconds (default 120).

    Returns
    -------
    dict
        ``{"rooms_modified": int, "output": str, "elapsed_s": float}``

    Raises
    ------
    RuntimeError
        If compilation fails, the Java tool exits non-zero, or the output file
        is not produced.
    FileNotFoundError
        If ``home_path`` does not exist.
    """
    home_path = str(Path(home_path).resolve())
    if not Path(home_path).exists():
        raise FileNotFoundError(f"Source .sh3d not found: {home_path}")

    # Always snapshot before mutating — even when out_path is supplied, take
    # a backup of the SOURCE so an accidental clobber stays reversible.
    from cli_anything.sweethome3d.core.backup import backup as _backup
    _backup(home_path)

    # Determine output path; use a tmp file for in-place overwrite
    in_place = out_path is None
    if in_place:
        tmp_fd, tmp_out = tempfile.mkstemp(suffix=".sh3d", prefix="modify_rooms_")
        os.close(tmp_fd)
        effective_out = tmp_out
    else:
        effective_out = str(Path(out_path).resolve())

    # Compile if needed
    sh3d_home, classes_dir = _ensure_compiled()

    # Write spec to a temp file
    spec_fd, spec_path = tempfile.mkstemp(suffix=".json", prefix="mr_spec_")
    try:
        with os.fdopen(spec_fd, "w") as f:
            json.dump(spec, f)

        java = _java_bin(sh3d_home)
        cp = _build_classpath(sh3d_home, classes_dir)

        cmd = [
            str(java),
            "-cp", cp,
            "ModifyRooms",
            "--in",   home_path,
            "--out",  effective_out,
            "--spec", spec_path,
        ]

        t0 = time.monotonic()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = time.monotonic() - t0

        if result.returncode != 0:
            raise RuntimeError(
                f"ModifyRooms exited with code {result.returncode}.\n"
                f"stdout:\n{result.stdout.strip()}\n"
                f"stderr:\n{result.stderr.strip()}"
            )

        # Extract the JSON summary from the last line of stdout
        summary: dict = {}
        lines = result.stdout.strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    summary = json.loads(line)
                except json.JSONDecodeError:
                    pass
                break

        if not Path(effective_out).exists():
            raise RuntimeError(
                f"ModifyRooms claimed success but output file not found: {effective_out}\n"
                f"stdout:\n{result.stdout.strip()}"
            )

        # In-place: atomically replace the source file
        if in_place:
            shutil.move(effective_out, home_path)
            effective_out = home_path

        return {
            "rooms_modified": summary.get("rooms_modified", -1),
            "output": effective_out,
            "elapsed_s": round(elapsed, 3),
        }

    except Exception:
        # Clean up tmp files on error
        if in_place and Path(effective_out).exists() and effective_out != home_path:
            try:
                os.unlink(effective_out)
            except OSError:
                pass
        raise
    finally:
        try:
            os.unlink(spec_path)
        except OSError:
            pass
