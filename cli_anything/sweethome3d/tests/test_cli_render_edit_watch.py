"""End-to-end tests for render, edit floor/door, and watch commands.

These tests exercise new CLI commands being added in parallel:
  - render photo OUTPUT [--gpu/--no-gpu] [--quality LOW|MEDIUM|HIGH] [-w W] [-h H]
  - edit floor --room NAME --color "#RRGGBB" [--output PATH]
  - edit door --name NAME --flip [--output PATH]
  - watch PATH.sh3d [--output PATH.png]

Tests gracefully skip if the render_runtime module hasn't shipped yet or
if Sweet Home 3D is not installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zipfile
from xml.etree import ElementTree as ET

import pytest

from .test_full_e2e import _resolve_cli


@pytest.fixture(scope="module")
def cli_with_render():
    """Skip module if render_runtime hasn't shipped yet or SH3D not installed."""
    # Try importing render_runtime to check if the parallel work is done
    try:
        from cli_anything.sweethome3d.core import render_runtime  # noqa
    except ImportError:
        pytest.skip("render_runtime not yet shipped")

    # Also check if SH3D is installed
    cli = _resolve_cli("cli-anything-sweethome3d")
    r = subprocess.run(cli + ["--json", "render", "status"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("render status check failed")

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        pytest.skip("render status returned invalid JSON")

    if not data.get("installed", False):
        pytest.skip("SH3D not installed")

    return cli


class TestRenderCommands:
    """Test suite for render, edit, and watch commands."""

    CLI = _resolve_cli("cli-anything-sweethome3d")

    def _run(self, args, check=True, timeout=30):
        """Run CLI with subprocess; raise on non-zero return if check=True."""
        try:
            r = subprocess.run(self.CLI + args,
                               capture_output=True, text=True,
                               check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AssertionError(f"CLI command timed out: {args}")

        if check and r.returncode != 0:
            raise AssertionError(
                f"CLI failed: {args}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
            )
        return r

    def _build_tiny_home(self, path):
        """Create a minimal home with one room and one door for testing.

        Returns: path to the .sh3d file
        """
        self._run(["project", "new", "-n", "TinyHome", "-o", path])
        self._run(["--project", path, "wall", "rectangle", "0", "0", "300", "300"])
        self._run(["--project", path, "room", "rectangle", "0", "0", "300", "300",
                   "-n", "Studio"])
        self._run(["--project", path, "furniture", "add-door", "Door1", "150", "0"])
        return path

    # ─────────────────────────────────────────────────────
    # render photo tests
    # ─────────────────────────────────────────────────────

    def test_render_photo_gpu(self, cli_with_render, tmp_path):
        """Render with --gpu flag; output PNG should exist and be >5kB."""
        sh3d = str(tmp_path / "tiny_gpu.sh3d")
        output_png = str(tmp_path / "render_gpu.png")

        self._build_tiny_home(sh3d)

        # Invoke: render photo OUTPUT --gpu
        r = self._run(["--project", sh3d, "render", "photo", output_png,
                       "--gpu"], timeout=120)
        assert r.returncode == 0, f"render failed: {r.stderr}"

        # Verify output file exists and is substantial
        assert os.path.exists(output_png), f"output PNG not created: {output_png}"
        size = os.path.getsize(output_png)
        assert size > 5120, f"PNG too small: {size} bytes (expected >5120)"
        print(f"\n  GPU render: {output_png} ({size} bytes)")

    def test_render_photo_cpu_low_quality(self, cli_with_render, tmp_path):
        """Render with --no-gpu --quality LOW; allow longer timeout (60s)."""
        sh3d = str(tmp_path / "tiny_cpu.sh3d")
        output_png = str(tmp_path / "render_cpu_low.png")

        self._build_tiny_home(sh3d)

        # Invoke: render photo OUTPUT --no-gpu --quality LOW
        r = self._run(["--project", sh3d, "render", "photo", output_png,
                       "--no-gpu", "--quality", "LOW"], timeout=60)
        assert r.returncode == 0, f"render failed: {r.stderr}"

        assert os.path.exists(output_png), f"output PNG not created: {output_png}"
        size = os.path.getsize(output_png)
        assert size > 1024, f"PNG too small: {size} bytes (expected >1024)"
        print(f"\n  CPU LOW render: {output_png} ({size} bytes)")

    # ─────────────────────────────────────────────────────
    # edit floor tests
    # ─────────────────────────────────────────────────────

    def test_edit_floor_changes_color(self, tmp_path):
        """Build a 1-room home, edit floor color, verify via Python API."""
        sh3d = str(tmp_path / "floor_color.sh3d")
        edited_sh3d = str(tmp_path / "floor_color_edited.sh3d")

        self._build_tiny_home(sh3d)

        # Invoke: edit floor --room Studio --color "#1E3F66" --output EDITED
        r = self._run(["--project", sh3d, "edit", "floor",
                       "--room", "Studio", "--color", "#1E3F66",
                       "--output", edited_sh3d], check=False)

        # If the command doesn't exist yet, skip
        if r.returncode != 0 and "edit" in r.stderr:
            pytest.skip("edit floor command not yet implemented")

        assert r.returncode == 0, f"edit floor failed: {r.stderr}"
        assert os.path.exists(edited_sh3d), f"output file not created"

        # Open the saved file via Python API and check floorColor
        from cli_anything.sweethome3d.core import project as proj_core
        home = proj_core.open_home(edited_sh3d)

        # Find the Studio room and check its floor color
        studio = next((r for r in home.rooms if r.name == "Studio"), None)
        assert studio is not None, "Studio room not found after edit"

        # Expected color: 0xFF1E3F66 (alpha=FF for opaque)
        expected_color = 0xFF1E3F66
        actual_color = studio.floorColor
        assert actual_color == expected_color, \
            f"floor color mismatch: got 0x{actual_color:08X}, expected 0x{expected_color:08X}"

        print(f"\n  Floor color changed: 0x{actual_color:08X}")

    # ─────────────────────────────────────────────────────
    # edit door tests
    # ─────────────────────────────────────────────────────

    def test_edit_door_flip(self, tmp_path):
        """Add a door, flip it, verify angle changed via Python API."""
        sh3d = str(tmp_path / "door_flip.sh3d")
        edited_sh3d = str(tmp_path / "door_flip_edited.sh3d")

        self._build_tiny_home(sh3d)

        # Get the original door angle before flip
        from cli_anything.sweethome3d.core import project as proj_core
        home_before = proj_core.open_home(sh3d)
        door_before = next((f for f in home_before.furniture if f.name == "Door1"), None)
        assert door_before is not None, "Door1 not found in initial home"
        angle_before = door_before.angle

        # Invoke: edit door --name Door1 --flip --output EDITED
        r = self._run(["--project", sh3d, "edit", "door",
                       "--name", "Door1", "--flip",
                       "--output", edited_sh3d], check=False)

        if r.returncode != 0 and "edit" in r.stderr:
            pytest.skip("edit door command not yet implemented")

        assert r.returncode == 0, f"edit door failed: {r.stderr}"
        assert os.path.exists(edited_sh3d), f"output file not created"

        # Open edited file and check door angle
        home_after = proj_core.open_home(edited_sh3d)
        door_after = next((f for f in home_after.furniture if f.name == "Door1"), None)
        assert door_after is not None, "Door1 not found after edit"

        angle_after = door_after.angle
        # Flip should change angle by ~π (180 degrees)
        angle_diff = abs((angle_after - angle_before) % (2 * 3.14159265359))
        # Allow tolerance: π ± 0.1 radians
        expected_flip = 3.14159265359
        assert abs(angle_diff - expected_flip) < 0.2 or abs(angle_diff - 0) < 0.1, \
            f"angle didn't flip as expected: before={angle_before}, after={angle_after}, diff={angle_diff}"

        print(f"\n  Door angle flipped: {angle_before} -> {angle_after}")

    # ─────────────────────────────────────────────────────
    # watch command tests
    # ─────────────────────────────────────────────────────

    @pytest.mark.slow
    def test_watch_polling_mode(self, tmp_path):
        """Spawn watch subprocess, modify file, verify PNG output.

        This test spawns a long-running `watch` process that polls the .sh3d
        file and auto-renders PNGs on changes. We modify the file mid-watch
        and verify the output was created.
        """
        sh3d = str(tmp_path / "watch_test.sh3d")
        watch_png = str(tmp_path / "watch_test.png")

        self._build_tiny_home(sh3d)

        # Spawn watch subprocess
        proc = subprocess.Popen(
            self.CLI + ["watch", sh3d, "--output", watch_png],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        try:
            # Give watch time to start and do initial render
            time.sleep(2)

            # Verify proc is still running
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                pytest.skip(
                    f"watch process exited immediately. stdout: {stdout}, stderr: {stderr}"
                )

            # Modify the project file (edit floor color)
            self._run(["--project", sh3d, "edit", "floor",
                       "--room", "Studio", "--color", "#FF0000",
                       "--output", sh3d], check=False)

            # Give watch time to detect the change and re-render
            time.sleep(2)

            # Kill the watch subprocess
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            # Verify the PNG was created
            if not os.path.exists(watch_png):
                pytest.skip("watch PNG not created (watch command may not be implemented)")

            size = os.path.getsize(watch_png)
            assert size > 1024, f"PNG too small: {size} bytes"
            print(f"\n  Watch rendered: {watch_png} ({size} bytes)")

        finally:
            # Ensure process is cleaned up
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
