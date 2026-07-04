"""Adversarial bug-hunt regression tests for cli-anything-sweethome3d.

Each test exercises a real bug that was found by round-tripping generated
.sh3d files through Sweet Home 3D's own reader (DefaultHomeInputStream).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from cli_anything.sweethome3d.core import project as proj_core
from cli_anything.sweethome3d.core.model import (
    FurnitureGroup,
    Home,
    PieceOfFurniture,
    Point,
    Room,
    Texture,
)


def _sh3d_jar() -> str:
    jar = os.environ.get("SWEETHOME3D_JAR") or os.path.join(
        os.environ.get("SWEETHOME3D_HOME", "/home/jon/sh3d/SweetHome3D-7.5"),
        "lib", "SweetHome3D.jar",
    )
    if not os.path.isfile(jar):
        pytest.skip(f"SweetHome3D.jar not found: {jar}")
    return jar


def _compile_validator(build_dir: Path) -> Path:
    jar = _sh3d_jar()
    src = Path(__file__).resolve().parents[3] / "tools" / "sh3d_validate" / "ValidateSh3d.java"
    cls = build_dir / "ValidateSh3d.class"
    if cls.exists() and cls.stat().st_mtime >= src.stat().st_mtime:
        return build_dir
    subprocess.run(
        ["javac", "-cp", jar, str(src), "-d", str(build_dir)],
        check=True, capture_output=True, text=True,
    )
    return build_dir


def run_sh3d_validator(sh3d_path: str) -> subprocess.CompletedProcess:
    """Load *sh3d_path* with SH3D's own DefaultHomeInputStream and return result."""
    jar = _sh3d_jar()
    build_dir = Path(tempfile.gettempdir()) / "sh3d_validate_build"
    build_dir.mkdir(parents=True, exist_ok=True)
    _compile_validator(build_dir)
    cp = f"{build_dir}:{jar}"
    return subprocess.run(
        ["java", "-cp", cp, "ValidateSh3d", sh3d_path],
        capture_output=True, text=True, timeout=30,
    )


class TestTextureWidthHeight:
    """Regression for texture elements missing required width/height attributes."""

    def test_texture_without_dimensions_adds_zero_defaults(self):
        h = Home()
        h.rooms.append(Room(
            points=[Point(0, 0), Point(100, 0), Point(100, 100)],
            floorTexture=Texture(name="oak", image="2"),
        ))
        tree = proj_core.home_to_xml(h)
        tex = tree.find("room/texture")
        assert tex is not None
        assert tex.get("width") is not None
        assert tex.get("height") is not None

    def test_texture_without_dimensions_opens_in_sh3d(self):
        h = Home()
        h.rooms.append(Room(
            points=[Point(0, 0), Point(100, 0), Point(100, 100)],
            floorTexture=Texture(name="oak", image="2"),
        ))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.sh3d")
            proj_core.save_home(h, p, extra_content={"2": b"\x89PNG\r\n\x1a\n"})
            r = run_sh3d_validator(p)
        assert r.returncode == 0, r.stderr.strip()
