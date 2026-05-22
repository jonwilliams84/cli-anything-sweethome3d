"""
Tests for render_runtime.render().

Run with:  pytest cli_anything/sweethome3d/tests/test_render_runtime.py -v
Slow CPU test can be skipped: SKIP_SLOW_RENDER=1 pytest ...
"""

import os
import shutil
import glob
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures / skip conditions
# ---------------------------------------------------------------------------

SH3D_HOME_ENV = os.environ.get("SWEETHOME3D_HOME", "")
SH3D_DEFAULT = Path("/home/jonwi/sh3d/SweetHome3D-7.5")
SH3D_AVAILABLE = bool(SH3D_HOME_ENV and Path(SH3D_HOME_ENV).is_dir()) or SH3D_DEFAULT.is_dir()

TEST_HOME = Path("/mnt/c/Users/jonwi/Documents/Bungalow-from-svg-v18-ready.sh3d")
BUNGALOW_SH3D = str(TEST_HOME)
HOME_AVAILABLE = TEST_HOME.exists()

# Also accept the v19 variant for gpu_photo test
_BUNGALOW_V19 = Path("/mnt/c/Users/jonwi/Documents/Bungalow-from-svg-v19-ready.sh3d")
BUNGALOW_V19_AVAILABLE = _BUNGALOW_V19.exists()


def _blender_available() -> bool:
    """Return True if a Blender binary can be found (without triggering auto-install)."""
    env_bin = os.environ.get("BLENDER_BIN")
    if env_bin and Path(env_bin).is_file():
        return True
    if shutil.which("blender"):
        return True
    for p in glob.glob("/opt/blender-*/blender"):
        if Path(p).is_file():
            return True
    for p in glob.glob("/mnt/c/Program Files/Blender Foundation/Blender */blender.exe"):
        if Path(p).is_file():
            return True
    cache_dir = Path.home() / ".cache" / "cli-anything-sweethome3d" / "blender"
    for p in glob.glob(str(cache_dir / "blender-*" / "blender")):
        if Path(p).is_file():
            return True
    return False


skip_no_sh3d = pytest.mark.skipif(
    not SH3D_AVAILABLE,
    reason="SweetHome3D not found (set SWEETHOME3D_HOME or ensure /home/jonwi/sh3d/SweetHome3D-7.5 exists)",
)
skip_no_home = pytest.mark.skipif(
    not HOME_AVAILABLE,
    reason=f"Test .sh3d file not found: {TEST_HOME}",
)
skip_slow = pytest.mark.skipif(
    os.environ.get("SKIP_SLOW_RENDER", "").strip() not in ("", "0"),
    reason="SKIP_SLOW_RENDER is set — skipping slow CPU render test",
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_sh3d
@skip_no_home
def test_gpu_render(tmp_path):
    """GPU render should produce a PNG larger than 5 kB."""
    from cli_anything.sweethome3d.core.render_runtime import render  # noqa: PLC0415

    out = tmp_path / "gpu_out.png"
    result = render(str(TEST_HOME), str(out), gpu=True)

    assert out.exists(), f"Output PNG not created at {out}"
    assert out.stat().st_size > 5_000, (
        f"Output PNG is suspiciously small ({out.stat().st_size} bytes)"
    )
    assert result["engine"] == "GpuRender"
    assert result["elapsed_s"] > 0
    assert result["width"] == 1400
    assert result["height"] == 900
    assert result["output"] == str(out.resolve())


@skip_no_sh3d
@skip_no_home
@skip_slow
@pytest.mark.slow
def test_cpu_render(tmp_path):
    """CPU render (Sunflow/LOW) should produce a PNG larger than 5 kB."""
    from cli_anything.sweethome3d.core.render_runtime import render  # noqa: PLC0415

    out = tmp_path / "cpu_out.png"
    result = render(str(TEST_HOME), str(out), gpu=False, quality="LOW")

    assert out.exists(), f"Output PNG not created at {out}"
    assert out.stat().st_size > 5_000, (
        f"Output PNG is suspiciously small ({out.stat().st_size} bytes)"
    )
    assert result["engine"] == "Render"
    assert result["elapsed_s"] > 0
    assert result["width"] == 1400
    assert result["height"] == 900


# ---------------------------------------------------------------------------
# gpu_photo (Blender Cycles) test
# ---------------------------------------------------------------------------

skip_no_blender = pytest.mark.skipif(
    not _blender_available(),
    reason="Blender not installed (set BLENDER_BIN or install to ~/.local/bin/blender)",
)

skip_no_sh3d_v19 = pytest.mark.skipif(
    not (SH3D_AVAILABLE and BUNGALOW_V19_AVAILABLE),
    reason=(
        "gpu_photo test requires SweetHome3D + "
        f"{_BUNGALOW_V19} (v19 bungalow file)"
    ),
)


# Bundled example .sh3d that ships with the harness — preferred over the
# user-specific Windows-mount paths above because it works on any machine
# that has the harness installed.
_EXAMPLE_SH3D = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "examples" / "Home-Clean-Base-RAL.sh3d"
)
EXAMPLE_AVAILABLE = _EXAMPLE_SH3D.is_file()
skip_no_example = pytest.mark.skipif(
    not EXAMPLE_AVAILABLE,
    reason=f"bundled example .sh3d not found at {_EXAMPLE_SH3D}",
)


@skip_no_blender
@skip_no_sh3d
@skip_no_example
@pytest.mark.slow
def test_gpu_photo_renders_bundled_example(tmp_path):
    """gpu_photo end-to-end smoke test against the bundled example .sh3d.

    Compiles ExportObj.java (or reuses the cached .class), exports the
    project to OBJ via SH3D's bundled JRE, then renders it in Blender
    Cycles. Output must be a valid PNG > 5 KB.
    """
    from cli_anything.sweethome3d.core.render_runtime import render  # noqa: PLC0415

    out = tmp_path / "example.png"
    r = render(
        str(_EXAMPLE_SH3D),
        str(out),
        engine="gpu_photo",
        samples=8,        # quick smoke render
        width=320,
        height=200,
        timeout_s=300,
    )

    assert out.exists(), f"Output PNG not created at {out}"
    assert out.stat().st_size > 5_000, (
        f"Output PNG is suspiciously small ({out.stat().st_size} bytes)"
    )
    # PNG magic bytes
    with open(out, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n", (
            "Output is not a valid PNG file"
        )
    assert r["engine"] == "BlenderCycles-OptiX"
    assert r["elapsed_s"] > 0
    assert r["width"] == 320
    assert r["height"] == 200
    assert r["samples"] == 8


@skip_no_blender
@skip_no_sh3d
@skip_no_sh3d_v19
@pytest.mark.slow
def test_gpu_photo_renders(tmp_path):
    """gpu_photo: OBJ export + Blender Cycles should produce a PNG > 5 kB."""
    from cli_anything.sweethome3d.core.render_runtime import render  # noqa: PLC0415

    # Use v19 if available; fall back to v18
    sh3d_path = str(_BUNGALOW_V19) if BUNGALOW_V19_AVAILABLE else BUNGALOW_SH3D

    out = tmp_path / "render.png"
    r = render(
        sh3d_path,
        str(out),
        engine="gpu_photo",
        samples=16,
        width=400,
        height=300,
        timeout_s=600,
    )

    assert r["engine"] == "BlenderCycles-OptiX", (
        f"Expected BlenderCycles-OptiX engine, got {r['engine']!r}"
    )
    assert out.exists(), f"Output PNG not created at {out}"
    assert out.stat().st_size > 5_000, (
        f"Output PNG is suspiciously small ({out.stat().st_size} bytes)"
    )
    assert r["elapsed_s"] > 0
    assert r["width"] == 400
    assert r["height"] == 300
    assert r["samples"] == 16
    assert r["output"] == str(out.resolve())
