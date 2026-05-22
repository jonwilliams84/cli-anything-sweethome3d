"""End-to-end tests: real CLI subprocess, real .sh3d files, real SVG output."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

import pytest


def _resolve_cli(name):
    """Resolve installed CLI; fall back to python -m for dev runs."""
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(
            f"{name} not found in PATH. Install with: pip install -e ."
        )
    module = "cli_anything.sweethome3d.sweethome3d_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", "cli_anything.sweethome3d"]


class TestCLISubprocess:
    CLI = _resolve_cli("cli-anything-sweethome3d")

    def _run(self, args, check=True):
        return subprocess.run(self.CLI + args,
                                capture_output=True, text=True, check=check)

    def test_help(self):
        r = self._run(["--help"])
        assert r.returncode == 0
        assert "Sweet Home 3D" in r.stdout

    def test_version(self):
        r = self._run(["--version"])
        assert r.returncode == 0
        assert "1.0.0" in r.stdout

    def test_project_new_json(self, tmp_path):
        out = str(tmp_path / "n.sh3d")
        r = self._run(["--json", "project", "new", "-n", "TestHouse",
                       "-o", out])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["created"] == out
        assert data["name"] == "TestHouse"
        assert data["version"] == 7400
        assert os.path.exists(out)

    def test_render_status_when_not_installed(self):
        env = os.environ.copy()
        # Clear any pointers so the binary truly looks missing
        for k in ("SWEETHOME3D_BIN", "SWEETHOME3D_JAR"):
            env.pop(k, None)
        r = subprocess.run(self.CLI + ["--json", "render", "status"],
                             capture_output=True, text=True, env=env)
        # Don't crash — return a useful JSON status either way.
        assert r.returncode == 0
        data = json.loads(r.stdout)
        # `installed` may be True if SH3D is actually installed (CI uncommon);
        # main contract: the key exists and the call succeeds.
        assert "installed" in data


class TestFullWorkflow:
    """Build a complete studio via the CLI and verify the output."""

    CLI = _resolve_cli("cli-anything-sweethome3d")

    def _run(self, args):
        r = subprocess.run(self.CLI + args, capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(
                f"CLI failed: {args}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
            )
        return r

    def test_studio_workflow(self, tmp_path):
        sh3d = str(tmp_path / "studio.sh3d")
        svg = str(tmp_path / "studio.svg")

        # 1. new project
        self._run(["project", "new", "-n", "Studio", "-o", sh3d])
        # 2. four walls
        self._run(["--project", sh3d, "wall", "rectangle", "0", "0",
                    "500", "400"])
        # 3. labelled room
        self._run(["--project", sh3d, "room", "rectangle", "0", "0",
                    "500", "400", "-n", "Studio", "--area-visible"])
        # 4. door + window + light
        self._run(["--project", sh3d, "furniture", "add-door",  "Door1",
                    "250", "0"])
        self._run(["--project", sh3d, "furniture", "add-window", "Win1",
                    "250", "400"])
        self._run(["--project", sh3d, "furniture", "add-light",
                    "Ceiling", "250", "200", "--power", "0.8"])
        # 5. dimension annotation
        self._run(["--project", sh3d, "dimension", "add", "0", "0",
                    "500", "0", "--offset", "40"])
        # 6. label
        self._run(["--project", sh3d, "label", "add", "North", "250", "50"])
        # 7. SVG export
        self._run(["--project", sh3d, "export", "svg", svg])

        # Verify the .sh3d ZIP structure: Home.xml plus numbered entries
        # for each catalog model/icon bundled in (matching SH3D's own
        # DefaultHomeOutputStream convention).
        with zipfile.ZipFile(sh3d) as z:
            names = z.namelist()
            assert "Home.xml" in names
            assert all(n == "Home.xml" or n.isdigit() for n in names), \
                f"unexpected entries: {names}"
            xml = z.read("Home.xml").decode("utf-8")
        # Schema sanity
        root = ET.fromstring(xml)
        assert root.tag == "home"
        assert root.get("version") == "7400"
        assert root.get("name") == "Studio"

        # Verify the SVG is well-formed and has the expected groups
        svg_root = ET.parse(svg).getroot()
        assert svg_root.tag.endswith("svg")
        ids = {g.get("id") for g in svg_root.findall(".//{*}g")}
        for required in ("rooms", "walls", "furniture", "dimensions",
                          "labels", "compass"):
            assert required in ids, f"missing <g id={required!r}> in SVG"

        # Verify counts via the CLI's --json project info
        r = self._run(["--project", sh3d, "--json", "project", "info"])
        info = json.loads(r.stdout)
        assert info["walls"] == 4
        assert info["rooms"] == 1
        assert info["doors_and_windows"] == 2
        assert info["lights"] == 1
        assert info["dimensionLines"] == 1
        assert info["labels"] == 1

        # Confirm SVG file exists and is non-trivial
        assert os.path.getsize(svg) > 500
        print(f"\n  .sh3d: {sh3d} ({os.path.getsize(sh3d)} bytes)")
        print(f"\n  .svg:  {svg}  ({os.path.getsize(svg)} bytes)")

    def test_dry_run_skips_save(self, tmp_path):
        sh3d = str(tmp_path / "dry.sh3d")
        self._run(["project", "new", "-n", "Dry", "-o", sh3d])
        # baseline: 0 walls
        before = json.loads(
            self._run(["--project", sh3d, "--json",
                        "project", "info"]).stdout)["walls"]
        # add a wall with --dry-run
        self._run(["--project", sh3d, "--dry-run",
                    "wall", "add", "0", "0", "100", "0"])
        # nothing changed on disk
        after = json.loads(
            self._run(["--project", sh3d, "--json",
                        "project", "info"]).stdout)["walls"]
        assert before == after == 0

    def test_undo_via_two_level_create(self, tmp_path):
        """Two-level workflow: add level, add walls, delete level with --keep-attached."""
        sh3d = str(tmp_path / "twolevel.sh3d")
        self._run(["project", "new", "-n", "Twol", "-o", sh3d])
        self._run(["--project", sh3d, "level", "add", "Ground"])
        self._run(["--project", sh3d, "level", "add", "First"])
        # add wall on the first level
        r = self._run(["--project", sh3d, "--json", "level", "list"])
        levels = json.loads(r.stdout)
        first = next(l for l in levels if l["name"] == "First")
        self._run(["--project", sh3d, "wall", "add", "0", "0", "100", "0",
                    "-l", first["id"]])
        # delete-level --keep-attached must fail since wall is attached
        proc = subprocess.run(self.CLI + ["--project", sh3d, "level",
                                            "delete", "First",
                                            "--keep-attached"],
                              capture_output=True, text=True)
        assert proc.returncode != 0
        # default delete detaches and succeeds
        self._run(["--project", sh3d, "level", "delete", "First"])
        info = json.loads(self._run(["--project", sh3d, "--json",
                                      "project", "info"]).stdout)
        assert info["levels"] == 1
        assert info["walls"] == 1


class TestSchemaRoundtrip:
    """Direct Python-level roundtrip — verify every entity type."""

    def test_complete_roundtrip(self, tmp_path):
        from cli_anything.sweethome3d.core import (
            annotations as ann,
            cameras as cam,
            environment as env,
            furniture as furn,
            levels as lvl,
            project as proj,
            rooms as rooms,
            walls as walls,
        )
        h = proj.new_home("Complete")
        # levels
        g = lvl.add_level(h, "Ground", elevation=0)
        f = lvl.add_level(h, "First", elevation=270)
        # walls + room
        walls.rectangle(h, 0, 0, 500, 400)
        rooms.add_rectangle_room(h, 0, 0, 500, 400, name="Studio",
                                   level=g.id, areaVisible=True)
        # furniture
        furn.add_piece(h, "Sofa", 200, 200, width=200, depth=80, height=80,
                        color=0xC8A878, level=g.id)
        furn.add_door(h, "Door1", 250, 0, level=g.id)
        furn.add_window(h, "Win1", 250, 400, level=g.id)
        furn.add_light(h, "Ceiling", 250, 200, level=g.id, power=0.7)
        # annotations
        ann.add_dimension(h, 0, 0, 500, 0)
        ann.add_label(h, "Studio plan v1", 50, 50)
        ann.add_polyline(h, [(50, 50), (450, 50), (450, 350)], thickness=2)
        ann.set_compass(h, x=450, y=50, northDirection=0.5,
                          latitude=51.5, longitude=-0.1)
        # environment
        env.set_environment(h, skyColor=0x87CEEB, groundColor=0x654321,
                              drawingMode="OUTLINE", wallsAlpha=0.1)
        env.set_photo_size(h, 800, 600)
        # cameras
        cam.set_camera(h, kind="observerCamera",
                         x=250, y=200, z=170, yaw=0, pitch=0)
        cam.activate_camera(h, "observerCamera")

        # roundtrip
        p = str(tmp_path / "complete.sh3d")
        proj.save_home(h, p)
        h2 = proj.open_home(p)

        info = proj.info(h2)
        assert info["levels"] == 2
        assert info["walls"] == 4
        assert info["rooms"] == 1
        assert info["furniture"] == 4
        assert info["doors_and_windows"] == 2
        assert info["lights"] == 1
        assert info["dimensionLines"] == 1
        assert info["labels"] == 1
        assert info["polylines"] == 1
        # camera active
        assert h2.camera == "observerCamera"
        # environment preserved
        assert h2.environment.skyColor == 0x87CEEB
        assert h2.environment.drawingMode == "OUTLINE"
        assert h2.environment.photoWidth == 800
        # compass preserved
        assert abs(h2.compass.latitude - 51.5) < 1e-6
        # furniture color/level preserved. The writer forces alpha=FF on
        # piece-color overrides (a bare 24-bit RGB would write as 0xXXXXXX
        # with alpha=00, rendering the piece invisible in SH3D).
        sofa = next(f for f in h2.furniture if f.name == "Sofa")
        assert (sofa.color & 0xFFFFFF) == 0xC8A878
        assert sofa.level == g.id

        print(f"\n  Complete roundtrip OK: {p} ({os.path.getsize(p)} bytes)")


class TestImportSvg:
    """CLI `import svg` subcommand — minimal fixture-based smoke test."""

    CLI = _resolve_cli("cli-anything-sweethome3d")

    def _run(self, args, check=True):
        return subprocess.run(self.CLI + args,
                              capture_output=True, text=True, check=check)

    # ------------------------------------------------------------------
    # Minimal SVG that the importer accepts: a single black filled rect
    # acting as a wall-outline polygon (no rooms, no openings, no lights).
    # ------------------------------------------------------------------
    _MINIMAL_SVG = """\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400">
  <path fill="#000000"
        d="M 10,10 L 590,10 L 590,390 L 10,390 Z
           M 50,50 L 550,50 L 550,350 L 50,350 Z"/>
</svg>
"""

    _MINIMAL_SPEC = """\
meta:
  name: MinimalImport
  output: null
input:
  floors:
    - level: Ground
      svg: floor.svg
"""

    def _write_fixture(self, tmp_path):
        """Write the spec + SVG fixture files; return spec path."""
        svg_path = tmp_path / "floor.svg"
        svg_path.write_text(self._MINIMAL_SVG, encoding="utf-8")
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(self._MINIMAL_SPEC, encoding="utf-8")
        return str(spec_path)

    def test_import_svg_creates_file(self, tmp_path):
        """import svg --spec ... --output ... produces a valid .sh3d ZIP."""
        spec = self._write_fixture(tmp_path)
        out = str(tmp_path / "imported.sh3d")
        r = self._run(["import", "svg", "--spec", spec, "--output", out])
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert os.path.exists(out), "output file not created"
        assert os.path.getsize(out) > 0
        with zipfile.ZipFile(out) as z:
            assert "Home.xml" in z.namelist()

    def test_import_svg_json_output(self, tmp_path):
        """--json flag returns a dict with the expected keys."""
        spec = self._write_fixture(tmp_path)
        out = str(tmp_path / "json_test.sh3d")
        r = self._run(["--json", "import", "svg", "--spec", spec,
                       "--output", out])
        assert r.returncode == 0, f"stderr: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["created"] == out
        assert data["name"] == "MinimalImport"
        assert isinstance(data["levels"], int)
        assert isinstance(data["walls"], int)
        assert isinstance(data["rooms"], int)

    def test_import_svg_name_override(self, tmp_path):
        """--name overrides meta.name from the spec."""
        spec = self._write_fixture(tmp_path)
        out = str(tmp_path / "named.sh3d")
        r = self._run(["--json", "import", "svg", "--spec", spec,
                       "--output", out, "--name", "OverrideName"])
        assert r.returncode == 0, f"stderr: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["name"] == "OverrideName"
        # Verify the name is persisted in the .sh3d XML
        with zipfile.ZipFile(out) as z:
            xml = z.read("Home.xml").decode("utf-8")
        root = ET.fromstring(xml)
        assert root.get("name") == "OverrideName"

    def test_import_svg_output_fallback(self, tmp_path):
        """When --output is omitted the file is derived from meta.name."""
        spec = self._write_fixture(tmp_path)
        # Run from tmp_path so the fallback file lands there
        r = subprocess.run(
            self.CLI + ["import", "svg", "--spec", spec],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"
        expected = tmp_path / "MinimalImport.sh3d"
        assert expected.exists(), (
            f"expected fallback file {expected} — cwd files: "
            f"{list(tmp_path.iterdir())}"
        )
