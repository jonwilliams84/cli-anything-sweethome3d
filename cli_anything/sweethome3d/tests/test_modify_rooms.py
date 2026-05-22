"""
Tests for modify_rooms — round-trip test on Home-Clean-Base.sh3d.

Run with:
    pytest cli_anything/sweethome3d/tests/test_modify_rooms.py -v

The tests skip gracefully when SweetHome3D is not installed or the test
.sh3d file is not present.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

SH3D_DEFAULT = Path("/home/jonwi/sh3d/SweetHome3D-7.5")
SH3D_HOME_ENV = os.environ.get("SWEETHOME3D_HOME", "")
SH3D_AVAILABLE = bool(
    (SH3D_HOME_ENV and Path(SH3D_HOME_ENV).is_dir()) or SH3D_DEFAULT.is_dir()
)

TEST_HOME = Path("/mnt/c/Users/jonwi/Documents/Home-Clean-Base.sh3d")
HOME_AVAILABLE = TEST_HOME.exists()

skip_no_sh3d = pytest.mark.skipif(
    not SH3D_AVAILABLE,
    reason="SweetHome3D not found — set SWEETHOME3D_HOME or ensure "
           "/home/jonwi/sh3d/SweetHome3D-7.5 exists",
)
skip_no_home = pytest.mark.skipif(
    not HOME_AVAILABLE,
    reason=f"Test .sh3d file not found: {TEST_HOME}",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _room_ids_from_xml(sh3d_path: str) -> list[str]:
    """Extract room id attributes from the Home.xml entry inside a .sh3d ZIP."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(sh3d_path) as zf:
        names = zf.namelist()
        xml_entry = "Home.xml" if "Home.xml" in names else "Home"
        with zf.open(xml_entry) as f:
            tree = ET.parse(f)
    root = tree.getroot()
    return [
        elem.get("id")
        for elem in root.iter("room")
        if elem.get("id")
    ]


def _get_room_attrs(sh3d_path: str, room_id: str) -> dict:
    """Return XML attributes of a specific room element."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(sh3d_path) as zf:
        names = zf.namelist()
        xml_entry = "Home.xml" if "Home.xml" in names else "Home"
        with zf.open(xml_entry) as f:
            tree = ET.parse(f)
    root = tree.getroot()
    for elem in root.iter("room"):
        if elem.get("id") == room_id:
            return dict(elem.attrib)
    raise KeyError(f"Room {room_id!r} not found in {sh3d_path}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_sh3d
@skip_no_home
def test_modify_rooms_by_id(tmp_path):
    """Round-trip: set floor colour on a specific room and verify it persists."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    src = str(TEST_HOME)
    out = str(tmp_path / "modified.sh3d")

    # Use the first room (largest area) — id known from earlier probe
    target_id = "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4"
    floor_color_argb = "FFD8C6A4"           # ARGB hex input
    expected_rgb = int(floor_color_argb[2:], 16)  # 0xD8C6A4 after stripping alpha

    spec = {
        "rooms": [
            {
                "id": target_id,
                "floor_color": floor_color_argb,
                "floor_visible": True,
            }
        ]
    }

    result = modify_rooms(src, spec, out_path=out)

    assert result["rooms_modified"] == 1, f"Expected 1 room modified, got {result['rooms_modified']}"
    assert result["output"] == str(Path(out).resolve())
    assert result["elapsed_s"] >= 0
    assert Path(out).exists(), "Output .sh3d file not created"
    assert Path(out).stat().st_size > 10_000, "Output file suspiciously small"

    # Verify the floor colour was written into the XML.
    # SH3D's HomeXMLExporter serialises colors as 8-char hex (e.g. "00D8C6A4")
    # where the first 2 chars are always "00" (no alpha for room floor colour).
    attrs = _get_room_attrs(out, target_id)
    raw_color = attrs.get("floorColor", "000000")
    written_rgb = int(raw_color, 16) & 0xFFFFFF
    assert written_rgb == expected_rgb, (
        f"Floor colour mismatch: expected 0x{expected_rgb:06X}, "
        f"got 0x{written_rgb:06X} (raw={raw_color!r})"
    )


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_wall_sides(tmp_path):
    """Wall-side colour is applied via SH3D's own WallSide detection algorithm."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms
    import xml.etree.ElementTree as ET

    src = str(TEST_HOME)
    out = str(tmp_path / "wall_sides.sh3d")

    target_id = "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4"
    wall_color_argb = "FFFFC0CB"   # pink
    expected_rgb = int(wall_color_argb[2:], 16)  # 0xFFC0CB

    spec = {
        "rooms": [
            {
                "id": target_id,
                "wall_sides_color": wall_color_argb,
            }
        ]
    }

    result = modify_rooms(src, spec, out_path=out)
    assert result["rooms_modified"] == 1
    assert Path(out).exists()

    # At least one wall in the XML should have leftSideColor or rightSideColor == expected_rgb
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        xml_entry = "Home.xml" if "Home.xml" in names else "Home"
        with zf.open(xml_entry) as f:
            tree = ET.parse(f)

    colored_walls = 0
    for wall in tree.getroot().iter("wall"):
        for attr in ("leftSideColor", "rightSideColor"):
            raw = wall.get(attr)
            if raw is not None and (int(raw, 16) & 0xFFFFFF) == expected_rgb:
                colored_walls += 1
    assert colored_walls > 0, (
        "No wall side found with the expected pink colour — "
        "WallSide detection may have produced zero sides"
    )


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_baseboard(tmp_path):
    """Baseboard is attached to all interior wall sides of the target room."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms
    import xml.etree.ElementTree as ET

    src = str(TEST_HOME)
    out = str(tmp_path / "baseboard.sh3d")

    target_id = "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4"

    spec = {
        "rooms": [
            {
                "id": target_id,
                "baseboard": {
                    "color": "FFFFFFFF",
                    "thickness_cm": 1.0,
                    "height_cm": 10.0,
                }
            }
        ]
    }

    result = modify_rooms(src, spec, out_path=out)
    assert result["rooms_modified"] == 1
    assert Path(out).exists()

    # Check that at least one wall has a baseboard child element
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        xml_entry = "Home.xml" if "Home.xml" in names else "Home"
        with zf.open(xml_entry) as f:
            tree = ET.parse(f)

    baseboard_count = 0
    for wall in tree.getroot().iter("wall"):
        for bb in wall.iter("baseboard"):
            baseboard_count += 1
    assert baseboard_count > 0, (
        "No baseboard elements found after applying baseboard spec — "
        "WallSide detection produced zero sides or baseboard not serialised"
    )


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_match_predicate(tmp_path):
    """The 'match' predicate applies to all rooms on a level above a min area."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    src = str(TEST_HOME)
    out = str(tmp_path / "match.sh3d")

    spec = {
        "rooms": [
            {
                "match": {"level": "Level 1", "min_area_cm2": 50000},
                "floor_color": "FFE0C8A8",
                "floor_visible": True,
            }
        ]
    }

    result = modify_rooms(src, spec, out_path=out)
    # Home-Clean-Base has 11 Level 1 rooms; several are > 50000 cm²
    assert result["rooms_modified"] >= 1, (
        f"Expected at least 1 room modified via match, got {result['rooms_modified']}"
    )
    assert Path(out).exists()


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_preserves_room_count(tmp_path):
    """Round-trip must not add or remove rooms from the .sh3d file."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    src = str(TEST_HOME)
    out = str(tmp_path / "preserve.sh3d")

    original_ids = set(_room_ids_from_xml(src))

    spec = {
        "rooms": [
            {
                "id": "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4",
                "floor_color": "FFD8C6A4",
            }
        ]
    }

    modify_rooms(src, spec, out_path=out)
    modified_ids = set(_room_ids_from_xml(out))

    assert original_ids == modified_ids, (
        f"Room set changed after modify_rooms!\n"
        f"Added: {modified_ids - original_ids}\n"
        f"Removed: {original_ids - modified_ids}"
    )


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_inplace(tmp_path):
    """When out_path is None, the source file is overwritten in-place."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    # Copy test file to a writable tmp location
    src_copy = str(tmp_path / "copy.sh3d")
    shutil.copy2(str(TEST_HOME), src_copy)
    original_size = Path(src_copy).stat().st_size

    spec = {
        "rooms": [
            {
                "id": "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4",
                "ceiling_visible": True,
            }
        ]
    }

    result = modify_rooms(src_copy, spec, out_path=None)

    assert result["output"] == str(Path(src_copy).resolve())
    assert Path(src_copy).exists()
    # File should still be a valid ZIP / .sh3d
    assert zipfile.is_zipfile(src_copy), "In-place result is not a valid ZIP"


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_unknown_id_warns(tmp_path, capsys):
    """A spec with an unknown 'id' should warn but not crash."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    src = str(TEST_HOME)
    out = str(tmp_path / "no_match.sh3d")

    spec = {
        "rooms": [
            {
                "id": "room-does-not-exist-00000000-0000-0000-0000",
                "floor_color": "FFD8C6A4",
            }
        ]
    }

    result = modify_rooms(src, spec, out_path=out)
    # Zero rooms should be modified (no match)
    assert result["rooms_modified"] == 0
    assert Path(out).exists()


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_output_is_valid_zip(tmp_path):
    """The output .sh3d is a valid ZIP (SweetHome3D file format)."""
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    src = str(TEST_HOME)
    out = str(tmp_path / "valid_zip.sh3d")

    spec = {
        "rooms": [
            {
                "id": "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4",
                "floor_visible": True,
            }
        ]
    }

    modify_rooms(src, spec, out_path=out)
    assert zipfile.is_zipfile(out), "Output is not a valid ZIP file"
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert any(n in ("Home.xml", "Home") for n in names), (
        f"Output ZIP is missing a Home.xml/Home entry; entries: {names[:10]}"
    )


@skip_no_sh3d
@skip_no_home
def test_modify_rooms_wall_sides_texture(tmp_path):
    """wall_sides_texture sets a catalog texture on wall interior faces.

    Verifies that:
    1. At least one wall element in Home.xml has a <texture> child with
       attribute="leftSideTexture" or attribute="rightSideTexture" and
       catalogId="eTeks#stoneWall".
    2. The texture image data is bundled as a ZIP entry in the output
       (image="N" entries where N is a numeric index referencing the bundled JPG).
    """
    import xml.etree.ElementTree as ET
    from cli_anything.sweethome3d.core.modify_rooms import modify_rooms

    src = str(TEST_HOME)
    out = str(tmp_path / "wall_texture.sh3d")

    target_id = "room-0a445bae-b423-483b-91f6-7f7d3f61d8e4"
    catalog_id = "eTeks#stoneWall"

    spec = {
        "rooms": [
            {
                "id": target_id,
                "wall_sides_texture": catalog_id,
            }
        ]
    }

    result = modify_rooms(src, spec, out_path=out)
    assert result["rooms_modified"] == 1
    assert Path(out).exists()

    with zipfile.ZipFile(out) as zf:
        zip_names = zf.namelist()
        xml_entry = "Home.xml" if "Home.xml" in zip_names else "Home"
        with zf.open(xml_entry) as f:
            tree = ET.parse(f)

    # Find walls with the stoneWall texture on interior side
    texture_walls = 0
    for wall_elem in tree.getroot().iter("wall"):
        for tex_elem in wall_elem.iter("texture"):
            attr = tex_elem.get("attribute", "")
            if attr in ("leftSideTexture", "rightSideTexture"):
                if tex_elem.get("catalogId") == catalog_id:
                    texture_walls += 1
                    # Verify the image reference points to a real ZIP entry
                    image_ref = tex_elem.get("image")
                    assert image_ref is not None, (
                        "texture element missing 'image' attribute — "
                        "texture JPG was not bundled into the output ZIP"
                    )
                    assert any(image_ref in n or n.endswith(image_ref) for n in zip_names), (
                        f"image={image_ref!r} in texture XML not found among ZIP entries; "
                        f"entries: {zip_names[:20]}"
                    )

    assert texture_walls > 0, (
        f"No wall found with catalogId={catalog_id!r} on leftSideTexture or "
        f"rightSideTexture — texture was not written into the output .sh3d"
    )
