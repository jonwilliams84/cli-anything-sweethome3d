"""Regression tests for security-fix changes.

B405 (rooms.py, walls.py):
    Verify the SVG modules import ET from defusedxml, not the bare
    xml.etree.ElementTree, and that type-annotation-only imports are
    guarded so the module can still be imported at runtime.

B112 (blender_render.py):
    Verify that _geometry_bounds narrows the caught-exception set
    so that KeyboardInterrupt and SystemExit propagate correctly.
"""

import os
import re

import pytest


# ---------------------------------------------------------------------------
# B405 — rooms.py  (type-annotation-only ET import from defusedxml)
# ---------------------------------------------------------------------------

class TestRoomsSecurityFix:
    """B405 fix: rooms.py must not trigger xml.etree.ElementTree."""

    def test_module_imports_defusedxml_not_bare_et(self):
        """rooms.py must import ET from defusedxml, not xml.etree.ElementTree."""
        from cli_anything.sweethome3d.core.svg import rooms as rooms_mod

        rooms_src = inspect.getsource(rooms_mod)
        assert "from defusedxml" in rooms_src
        assert "import xml.etree.ElementTree" not in rooms_src

    def test_rooms_module_loads_without_bare_et_in_namespace(self):
        """rooms.ET must come from defusedxml, not xml.etree.ElementTree."""
        from cli_anything.sweethome3d.core.svg import rooms as rooms_mod

        assert hasattr(rooms_mod, "ET")
        et_name = getattr(rooms_mod.ET, "__name__", None)
        assert et_name == "defusedxml.ElementTree", (
            f"rooms.ET must be defusedxml's ElementTree, got: {et_name}"
        )

    def test_extract_room_labels_accepts_stdlib_element(self):
        """extract_room_labels works when called with an xml.etree.Element."""
        import xml.etree.ElementTree as xET

        svg_xml = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text x="100" y="200" font-size="16">Kitchen</text>'
            '</svg>'
        )
        root = xET.fromstring(svg_xml)

        from cli_anything.sweethome3d.core.svg.rooms import extract_room_labels
        labels = extract_room_labels(root)
        assert isinstance(labels, list)

    def test_extract_room_labels_does_not_raise_on_annotation_et(self):
        """Type-annotation-only ET import must not break runtime calls."""
        from cli_anything.sweethome3d.core.svg.rooms import extract_room_labels
        import xml.etree.ElementTree as xET

        root = xET.Element("{http://www.w3.org/2000/svg}svg")
        result = extract_room_labels(root)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# B405 — walls.py  (type-annotation-only ET import from defusedxml)
# ---------------------------------------------------------------------------

class TestWallsSecurityFix:
    """B405 fix: walls.py must not trigger xml.etree.ElementTree."""

    def test_module_imports_defusedxml_not_bare_et(self):
        """walls.py must import ET from defusedxml, not xml.etree.ElementTree."""
        from cli_anything.sweethome3d.core.svg import walls as walls_mod

        walls_src = inspect.getsource(walls_mod)
        assert "from defusedxml" in walls_src
        assert "import xml.etree.ElementTree" not in walls_src

    def test_walls_module_loads_without_bare_et_in_namespace(self):
        """walls.ET must come from defusedxml, not xml.etree.ElementTree."""
        from cli_anything.sweethome3d.core.svg import walls as walls_mod

        assert hasattr(walls_mod, "ET")
        et_name = getattr(walls_mod.ET, "__name__", None)
        assert et_name == "defusedxml.ElementTree", (
            f"walls.ET must be defusedxml's ElementTree, got: {et_name}"
        )

    def test_extract_walls_does_not_raise_on_annotation_et(self):
        """Type-annotation-only ET import must not break runtime calls."""
        from cli_anything.sweethome3d.core.svg.walls import extract_walls
        import xml.etree.ElementTree as xET

        root = xET.Element("{http://www.w3.org/2000/svg}svg")
        result = extract_walls(root)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# B112 — blender_render.py  (narrow except to AttributeError, RuntimeError)
# ---------------------------------------------------------------------------

import inspect  # noqa: E402  (needed by other test classes above)


class TestBlenderRenderSecurityFix:
    """B112 fix: _geometry_bounds must not swallow KeyboardInterrupt/SystemExit."""

    @staticmethod
    def _read_geometry_bounds_source() -> str:
        """Read _geometry_bounds source directly from the file,
        avoiding import of blender_render (which requires Blender)."""
        test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(test_dir, "render", "blender_render.py")
        src = open(filepath).read()
        idx = src.find("def _geometry_bounds(")
        if idx == -1:
            return ""
        end = src.find("\ndef ", idx + 1)
        if end == -1:
            end = len(src)
        return src[idx:end]

    def test_geometry_bounds_source_has_no_bare_except(self):
        """_geometry_bounds must not contain 'except Exception:'."""
        src = self._read_geometry_bounds_source()
        assert src, "_geometry_bounds not found in blender_render.py"
        assert "except Exception:" not in src, (
            "_geometry_bounds must not catch bare Exception — "
            "it swallows KeyboardInterrupt and SystemExit (B112)"
        )

    def test_geometry_bounds_source_has_narrowed_except(self):
        """_geometry_bounds must catch AttributeError and RuntimeError only."""
        src = self._read_geometry_bounds_source()
        assert src, "_geometry_bounds not found in blender_render.py"
        assert "except (AttributeError, RuntimeError):" in src, (
            "_geometry_bounds must narrow to 'except (AttributeError, RuntimeError):' "
            "to avoid swallowing KeyboardInterrupt / SystemExit"
        )

    def test_geometry_bounds_signature_matches(self):
        """Verify _geometry_bounds takes no required arguments."""
        src = self._read_geometry_bounds_source()
        assert src, "_geometry_bounds not found in blender_render.py"
        m = re.match(r"def _geometry_bounds\((.*?)\):", src)
        assert m, f"Could not parse signature: {src[:80]}"
        params = m.group(1).strip()
        assert params == "", (
            f"_geometry_bounds signature changed: def _geometry_bounds({params})"
        )
