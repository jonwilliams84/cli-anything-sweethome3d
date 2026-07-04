"""Adversarial bug-hunt regression tests for cli-anything-sweethome3d.

Each test exercises a real bug that was found by round-tripping generated
.sh3d files through Sweet Home 3D's own reader (DefaultHomeInputStream).
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
import zipfile
import subprocess
import tempfile
from pathlib import Path

import pytest

from cli_anything.sweethome3d.core import project as proj_core
from cli_anything.sweethome3d.core.model import (
    Transformation,
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


class TestEmptyFurnitureGroup:
    """Regression for empty furniture groups crashing SH3D's reader."""

    def test_empty_furnituregroup_not_serialized(self):
        h = Home()
        h.furnitureGroups.append(FurnitureGroup(name="Empty", furniture=[]))
        tree = proj_core.home_to_xml(h)
        assert tree.find("furnitureGroup") is None

    def test_empty_nested_furnituregroup_not_serialized(self):
        h = Home()
        inner = FurnitureGroup(name="InnerEmpty", furniture=[])
        h.furnitureGroups.append(FurnitureGroup(
            name="Outer",
            furniture=[PieceOfFurniture(name="P", x=0, y=0, width=10, depth=10, height=10), inner],
        ))
        tree = proj_core.home_to_xml(h)
        outer = tree.find("furnitureGroup")
        assert outer is not None
        assert outer.find("furnitureGroup") is None
        assert outer.find("pieceOfFurniture") is not None

    def test_home_with_empty_group_opens_in_sh3d(self):
        h = Home()
        h.furnitureGroups.append(FurnitureGroup(name="Empty", furniture=[]))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "empty_group.sh3d")
            proj_core.save_home(h, p)
            r = run_sh3d_validator(p)
        assert r.returncode == 0, r.stderr.strip()


class TestSaveHomePathLike:
    """Regression for save_home rejecting pathlib.Path objects."""

    def test_save_home_accepts_pathlib_path(self):
        h = Home(name="pathlike")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pathlike.sh3d"
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.name == "pathlike"


class TestTransformationMatrixValidation:
    """Regression for invalid transformation matrices producing unreadable SH3D files."""

    def test_short_matrix_raises_valueerror(self):
        with pytest.raises(ValueError, match="12"):
            Transformation(name="arm", matrix="1 0 0 0 1 0 0 0 1")

    def test_long_matrix_raises_valueerror(self):
        with pytest.raises(ValueError, match="12"):
            Transformation(name="arm", matrix="1 0 0 0 0 1 0 0 0 0 1 0 0")

    def test_valid_matrix_opens_in_sh3d(self):
        h = Home()
        h.furniture.append(PieceOfFurniture(
            name="Chair", x=50, y=50, width=50, depth=50, height=80,
            catalogId="eTeks#chair",
            modelTransformations=[Transformation(
                name="arm",
                matrix="1 0 0 0 0 1 0 0 0 0 1 0",
            )],
        ))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "transform.sh3d")
            proj_core.save_home(h, p)
            r = run_sh3d_validator(p)
        assert r.returncode == 0, r.stderr.strip()


class TestFurnitureGroupCatalogContent:
    """Regression for catalog pieces inside furniture groups losing their model/icon."""

    def test_grouped_catalog_piece_keeps_model_and_icon(self):
        h = Home()
        grp = FurnitureGroup(name="Doors")
        grp.furniture.append(
            PieceOfFurniture(
                name="Front door", x=0, y=0,
                width=80, depth=6, height=200,
                catalogId="eTeks#door",
            )
        )
        h.furnitureGroups.append(grp)

        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "grp_catalog.sh3d")
            proj_core.save_home(h, p)

            with zipfile.ZipFile(p) as z:
                names = set(z.namelist())
                root = ET.fromstring(z.read("Home.xml"))

            piece_el = root.find(".//furnitureGroup/pieceOfFurniture")
            assert piece_el is not None
            model = piece_el.get("model")
            icon = piece_el.get("icon")
            assert model is not None, "grouped catalog piece lost its model reference"
            assert icon is not None, "grouped catalog piece lost its icon reference"
            assert model in names, f"model content entry {model} missing from .sh3d zip"
            assert icon in names, f"icon content entry {icon} missing from .sh3d zip"

            h2 = proj_core.open_home(p)
            g2 = h2.furnitureGroups[0]
            f2 = g2.furniture[0]
            assert f2.model == model
            assert f2.icon == icon

            r = run_sh3d_validator(p)
        assert r.returncode == 0, r.stderr.strip()
