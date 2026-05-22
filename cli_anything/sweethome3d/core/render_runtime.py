"""
render_runtime.py — library interface for SweetHome3D renders.

Compiles Render.java / GpuRender.java / ExportObj.java on first call
(per-process) into a per-user XDG cache dir, then invokes the bundled
SH3D JRE via subprocess.

Engines
-------
  gpu_draft  : SH3D GpuRender (Java3D/JOGL/OpenGL) — fast, no GI.
  cpu_photo  : SH3D Render (Sunflow) — slow, real GI.
  gpu_photo  : SH3D OBJ export → Blender Cycles+OptiX — GPU GI, photoreal.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import time
import warnings
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Internal state — compiled once per process
# ---------------------------------------------------------------------------
_compiled: bool = False
_classes_dir: Optional[Path] = None

# Path to blender_render.py (lives next to ExportObj.java in the render/ package)
BLENDER_SCRIPT = str(Path(__file__).parent.parent / "render" / "blender_render.py")


# ---------------------------------------------------------------------------
# Path discovery helpers
# ---------------------------------------------------------------------------

def _find_sh3d_home() -> Path:
    """Return the SweetHome3D installation directory."""
    env = os.environ.get("SWEETHOME3D_HOME")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
        raise RuntimeError(
            f"SWEETHOME3D_HOME is set to '{env}' but that directory does not exist."
        )
    default = Path("/home/jonwi/sh3d/SweetHome3D-7.5")
    if default.is_dir():
        return default
    raise RuntimeError(
        "SweetHome3D installation not found. "
        "Set the SWEETHOME3D_HOME environment variable to the installation directory "
        "(e.g. export SWEETHOME3D_HOME=/path/to/SweetHome3D-7.5)."
    )


def _find_javac() -> Path:
    """Return path to a javac binary, checking JAVA_HOME, /tmp/jdk8u402-b06, then PATH."""
    # 1. JAVA_HOME env var
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "javac"
        if candidate.is_file():
            return candidate
        raise RuntimeError(
            f"JAVA_HOME is set to '{java_home}' but {candidate} does not exist. "
            "Ensure JAVA_HOME points to a full JDK (not a JRE)."
        )

    # 2. Known download location
    bundled = Path("/tmp/jdk8u402-b06/bin/javac")
    if bundled.is_file():
        return bundled

    # 3. PATH
    which = shutil.which("javac")
    if which:
        return Path(which)

    raise RuntimeError(
        "No javac found. Options:\n"
        "  * Set JAVA_HOME to a JDK directory.\n"
        "  * Download a JDK: wget -qO- https://github.com/adoptium/temurin8-binaries/"
        "releases/download/jdk8u402-b06/OpenJDK8U-jdk_x64_linux_hotspot_8u402b06.tar.gz"
        " | tar -xz -C /tmp && mv /tmp/jdk8u402-b06 /tmp/jdk8u402-b06\n"
        "  * Or install via: sudo apt install default-jdk"
    )


def _java_sources_dir() -> Path:
    """Return the directory that contains Render.java, GpuRender.java, ExportObj.java."""
    # They live next to this file's package, in the render/ sibling directory.
    return Path(__file__).parent.parent / "render"


def _cache_dir() -> Path:
    """Return ~/.cache/cli-anything-sweethome3d/render/ (XDG-style)."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "cli-anything-sweethome3d" / "render"


def _classpath(sh3d_home: Path, classes_dir: Path) -> str:
    """Build a colon-separated classpath from SH3D jars + compiled classes dir."""
    jars = sorted(glob.glob(str(sh3d_home / "lib" / "*.jar")))
    if not jars:
        raise RuntimeError(
            f"No .jar files found under {sh3d_home / 'lib'}. "
            "Check your SWEETHOME3D_HOME path."
        )
    return ":".join(jars + [str(classes_dir)])


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def _needs_compile(src: Path, cls: Path) -> bool:
    """Return True if src is newer than cls (or cls doesn't exist)."""
    if not cls.exists():
        return True
    return src.stat().st_mtime > cls.stat().st_mtime


def _compile(sh3d_home: Path, classes_dir: Path) -> None:
    """Compile Render.java, GpuRender.java, and ExportObj.java into classes_dir if stale."""
    sources_dir = _java_sources_dir()
    javac = _find_javac()
    classes_dir.mkdir(parents=True, exist_ok=True)

    to_compile = []
    for name in ("Render", "GpuRender", "ExportObj"):
        src = sources_dir / f"{name}.java"
        cls = classes_dir / f"{name}.class"
        if not src.exists():
            if name == "ExportObj":
                # Agent A hasn't shipped yet — skip silently; gpu_photo will
                # raise a clear RuntimeError at call time.
                continue
            raise RuntimeError(
                f"Java source not found: {src}. "
                "Ensure the render/ package was installed correctly."
            )
        if _needs_compile(src, cls):
            to_compile.append(str(src))

    if not to_compile:
        return  # already up to date

    jars = sorted(glob.glob(str(sh3d_home / "lib" / "*.jar")))
    cp = ":".join(jars)
    cmd = [
        str(javac),
        "-source", "8", "-target", "8",
        "-cp", cp,
        "-d", str(classes_dir),
    ] + to_compile

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"javac compilation failed (exit {result.returncode}):\n"
            f"  command: {' '.join(cmd)}\n"
            f"  stdout: {result.stdout.strip()}\n"
            f"  stderr: {result.stderr.strip()}"
        )


# ---------------------------------------------------------------------------
# Blender discovery + auto-install
# ---------------------------------------------------------------------------

def _find_blender() -> str:
    """Locate a Blender binary.

    Discovery order:
      1. $BLENDER_BIN env var
      2. shutil.which("blender") on PATH
      3. ~/.local/bin/blender
      4. ~/.local/opt/blender-*/blender
      5. /opt/blender-*/blender
      6. /mnt/c/Program Files/Blender Foundation/Blender */blender.exe

    Raises RuntimeError with installation instructions if none found.
    Does NOT auto-install Blender.
    """
    # 1. env var
    env_bin = os.environ.get("BLENDER_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin

    # 2. PATH
    which_blender = shutil.which("blender")
    if which_blender:
        return which_blender

    # 3. ~/.local/bin/blender
    local_bin = Path.home() / ".local" / "bin" / "blender"
    if local_bin.is_file():
        return str(local_bin)

    # 4. ~/.local/opt/blender-*/blender
    for p in sorted(
        glob.glob(str(Path.home() / ".local" / "opt" / "blender-*" / "blender")),
        reverse=True,
    ):
        if Path(p).is_file():
            return p

    # 5. /opt/blender-*/blender
    for p in sorted(glob.glob("/opt/blender-*/blender"), reverse=True):
        if Path(p).is_file():
            return p

    # 6. Windows host (WSL)
    for p in sorted(
        glob.glob("/mnt/c/Program Files/Blender Foundation/Blender */blender.exe"),
        reverse=True,
    ):
        if Path(p).is_file():
            return p

    raise RuntimeError(
        "Blender binary not found. Install Blender 4.x and ensure it is on PATH, "
        "or set the BLENDER_BIN environment variable to the Blender executable path.\n"
        "Download from: https://www.blender.org/download/\n"
        "Example install:\n"
        "  tar -xJf blender-4.2.3-linux-x64.tar.xz -C ~/.local/opt/\n"
        "  ln -s ~/.local/opt/blender-4.2.3-linux-x64/blender ~/.local/bin/blender"
    )


# ---------------------------------------------------------------------------
# gpu_photo helpers
# ---------------------------------------------------------------------------

def _run_java_export_obj(sh3d_home: Path, classes_dir: Path,
                         home_path: str, obj_path: Path) -> None:
    """Run ExportObj to produce .obj, .mtl, .camera.json and textures dir."""
    export_obj_src = _java_sources_dir() / "ExportObj.java"
    if not export_obj_src.exists():
        raise RuntimeError(
            "ExportObj.java not found at "
            f"{export_obj_src}.\n"
            "Agent A (ExportObj.java) has not been delivered yet. "
            "The gpu_photo engine requires this file to be present in the render/ directory."
        )

    export_obj_cls = classes_dir / "ExportObj.class"
    if not export_obj_cls.exists():
        raise RuntimeError(
            f"ExportObj.class not compiled — expected at {export_obj_cls}. "
            "Try deleting the cache dir and re-running to force recompilation."
        )

    java_bin = sh3d_home / "runtime" / "bin" / "java"
    if not java_bin.exists():
        raise RuntimeError(f"SH3D bundled java not found at {java_bin}")

    lib_path = sh3d_home / "lib"
    cp = _classpath(sh3d_home, classes_dir)

    cmd = [
        str(java_bin),
        f"-Djava.library.path={lib_path}",
        "-cp", cp,
        "ExportObj",
        home_path,
        str(obj_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ExportObj exited with code {result.returncode}.\n"
            f"stdout:\n{result.stdout.strip()}\n"
            f"stderr:\n{result.stderr.strip()}"
        )


def _render_gpu_photo(
    home_path: str,
    output_path: str,
    *,
    samples: int,
    width: int,
    height: int,
    timeout_s: int,
) -> dict:
    """OBJ export via ExportObj.java → Blender Cycles+OptiX render."""
    blender = _find_blender()

    blender_script = Path(BLENDER_SCRIPT)
    if not blender_script.exists():
        raise RuntimeError(
            f"blender_render.py not found at {blender_script}.\n"
            "Agent B (blender_render.py) has not been delivered yet. "
            "The gpu_photo engine requires this file to be present in the render/ directory."
        )

    sh3d_home = _find_sh3d_home()

    # Ensure Java helpers are compiled
    global _compiled, _classes_dir
    if _classes_dir is None:
        _classes_dir = _cache_dir()
    if not _compiled:
        _compile(sh3d_home, _classes_dir)
        _compiled = True

    work = Path(tempfile.mkdtemp(prefix="sh3d-cycles-"))
    obj_path = work / "scene.obj"

    _run_java_export_obj(sh3d_home, _classes_dir, home_path, obj_path)

    cam_json = work / "scene.camera.json"
    cmd = [
        blender, "--background", "--python", str(blender_script),
        "--",
        str(obj_path), output_path,
        "--samples", str(samples),
        "--width", str(width),
        "--height", str(height),
        "--camera-json", str(cam_json),
    ]

    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    elapsed = time.monotonic() - t0

    if res.returncode != 0:
        raise RuntimeError(
            f"Blender render failed (exit {res.returncode}):\n"
            f"stdout:\n{res.stdout.strip()}\n"
            f"stderr:\n{res.stderr.strip()}"
        )

    out_file = Path(output_path)
    if not out_file.exists():
        raise RuntimeError(
            f"Blender claimed success but output file not found: {output_path}"
        )

    return {
        "engine": "BlenderCycles-OptiX",
        "elapsed_s": round(elapsed, 3),
        "output": str(out_file.resolve()),
        "width": width,
        "height": height,
        "samples": samples,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render(
    home_path: str,
    output_path: str,
    *,
    engine: str = "gpu_draft",
    gpu: Optional[bool] = None,        # deprecated — kept for back-compat
    quality: str = "LOW",
    width: int = 1400,
    height: int = 900,
    samples: int = 128,                # gpu_photo only
    timeout_s: int = 600,
) -> dict:
    """Run a SweetHome3D render.

    Parameters
    ----------
    home_path:   Path to the .sh3d file.
    output_path: Destination PNG path.
    engine:      "gpu_draft" | "cpu_photo" | "gpu_photo"
                   gpu_draft  — SH3D GpuRender (Java3D/JOGL/OpenGL); fast, no GI.
                   cpu_photo  — SH3D Render (Sunflow); slow, real GI.
                   gpu_photo  — OBJ export + Blender Cycles+OptiX; GPU GI, photoreal.
    gpu:         DEPRECATED. True → gpu_draft, False → cpu_photo.
                 Ignored when `engine` is explicitly set.
    quality:     CPU quality tier: "LOW" | "MEDIUM" | "HIGH" (cpu_photo only).
    width:       Output image width in pixels.
    height:      Output image height in pixels.
    samples:     Cycles sample count (gpu_photo only).
    timeout_s:   Subprocess timeout in seconds.

    Returns
    -------
    dict with keys: engine, elapsed_s, output, width, height, [samples].

    Raises
    ------
    RuntimeError on configuration problems or render failure.
    DeprecationWarning when `gpu` keyword is used.
    """
    global _compiled, _classes_dir

    # --- Back-compat: map deprecated `gpu` flag to engine name ---------------
    # We detect "engine was explicitly set" by checking whether the caller
    # provided a non-default value for engine.  Because gpu_draft is the
    # default, if gpu is also supplied we honour gpu only when engine is still
    # at its default value AND it wasn't explicitly passed as a kwarg.
    # The simplest safe approach: if gpu is not None, warn and map it ONLY when
    # engine is still the default "gpu_draft" (i.e., wasn't explicitly set).
    if gpu is not None:
        warnings.warn(
            "The `gpu` parameter of render() is deprecated. "
            "Use engine='gpu_draft' or engine='cpu_photo' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Only remap when engine is at its default
        if engine == "gpu_draft":
            engine = "gpu_draft" if gpu else "cpu_photo"

    # --- gpu_photo path -------------------------------------------------------
    if engine == "gpu_photo":
        return _render_gpu_photo(
            home_path, output_path,
            samples=samples, width=width, height=height, timeout_s=timeout_s,
        )

    # --- Legacy Java paths (gpu_draft / cpu_photo) ----------------------------
    sh3d_home = _find_sh3d_home()

    if _classes_dir is None:
        _classes_dir = _cache_dir()

    if not _compiled:
        _compile(sh3d_home, _classes_dir)
        _compiled = True

    if engine == "gpu_draft":
        java_engine = "GpuRender"
        use_gpu = True
    elif engine == "cpu_photo":
        java_engine = "Render"
        use_gpu = False
    else:
        raise ValueError(
            f"Unknown engine {engine!r}. Must be one of: gpu_draft, cpu_photo, gpu_photo."
        )

    java_bin = sh3d_home / "runtime" / "bin" / "java"
    if not java_bin.exists():
        raise RuntimeError(f"SH3D bundled java not found at {java_bin}")

    lib_path = sh3d_home / "lib"
    cp = _classpath(sh3d_home, _classes_dir)

    cmd = [
        str(java_bin),
        f"-Djava.library.path={lib_path}",
        "-cp", cp,
        java_engine,
        home_path,
        output_path,
        str(width),
        str(height),
    ]

    # Append quality arg for CPU renderer only
    if not use_gpu:
        quality_upper = quality.upper()
        if quality_upper not in ("LOW", "MEDIUM", "HIGH"):
            raise ValueError(f"quality must be LOW, MEDIUM, or HIGH; got {quality!r}")
        cmd.append(quality_upper)

    t0 = time.monotonic()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    elapsed = time.monotonic() - t0

    combined = result.stdout + result.stderr

    if result.returncode != 0:
        raise RuntimeError(
            f"{java_engine} exited with code {result.returncode}.\n"
            f"stdout:\n{result.stdout.strip()}\n"
            f"stderr:\n{result.stderr.strip()}"
        )

    # Confirm the renderer actually wrote the file
    wrote_line = next(
        (line for line in combined.splitlines() if line.strip().startswith("wrote ")),
        None,
    )
    if wrote_line is None:
        raise RuntimeError(
            f"{java_engine} did not print a 'wrote ...' confirmation line.\n"
            f"stdout:\n{result.stdout.strip()}\n"
            f"stderr:\n{result.stderr.strip()}"
        )

    out_file = Path(output_path)
    if not out_file.exists():
        raise RuntimeError(
            f"{java_engine} claimed success but output file not found: {output_path}"
        )

    return {
        "engine": java_engine,
        "elapsed_s": round(elapsed, 3),
        "output": str(out_file.resolve()),
        "width": width,
        "height": height,
    }
