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

import contextlib
import glob
import os
import shutil
import subprocess
import tempfile
import time
import warnings
from pathlib import Path
from typing import Iterable, Iterator, Optional


# ---------------------------------------------------------------------------
# Internal state — compiled once per process
# ---------------------------------------------------------------------------
_compiled: bool = False
_classes_dir: Optional[Path] = None


# ---------------------------------------------------------------------------
# Level-visibility filter (per-render)
# ---------------------------------------------------------------------------

def _resolve_level_specs(home, specs: Iterable[str]) -> set[str]:
    """Resolve a list of level identifiers (ids or names) to a set of level
    ids. Raises ValueError if any spec doesn't match a level.
    """
    by_id = {lvl.id: lvl for lvl in home.levels}
    by_name = {lvl.name: lvl for lvl in home.levels if lvl.name}
    resolved: set[str] = set()
    missing: list[str] = []
    for spec in specs:
        s = spec.strip()
        if not s:
            continue
        if s in by_id:
            resolved.add(s)
        elif s in by_name:
            resolved.add(by_name[s].id)
        else:
            missing.append(s)
    if missing:
        known = sorted(set(by_id) | set(by_name.keys()))
        raise ValueError(
            f"unknown level(s): {missing!r}. Known ids/names: {known!r}"
        )
    return resolved


@contextlib.contextmanager
def filtered_levels(
    home_path: str,
    *,
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    hide_ceilings: bool = False,
) -> Iterator[str]:
    """Yield a path to a temporary .sh3d with the requested level filter
    applied. Restored (file deleted) on exit.

    Resolution rules:
    - ``include``: only the named levels remain visible (others get
      ``level.visible=False``). Pass ids or names.
    - ``exclude``: the named levels are hidden; all others stay visible.
    - Pass at most one of the two. Passing neither yields the original
      path unchanged (no temp file is created).
    - ``hide_ceilings``: when True, every room on a still-visible level
      has its ``ceilingVisible`` flag set to False for this render.
    """
    if not include and not exclude and not hide_ceilings:
        yield home_path
        return
    if include and exclude:
        raise ValueError("filtered_levels: pass include OR exclude, not both")

    from cli_anything.sweethome3d.core.project import (  # noqa: PLC0415
        open_home, save_home,
    )

    home = open_home(home_path)
    if include or exclude:
        if include is not None:
            keep = _resolve_level_specs(home, include)
        else:
            drop = _resolve_level_specs(home, exclude or [])
            keep = {lvl.id for lvl in home.levels if lvl.id not in drop}
        if not keep:
            raise ValueError(
                "filtered_levels: filter resolved to zero visible levels — "
                "rendering would produce a sky-only image"
            )
        for lvl in home.levels:
            lvl.visible = lvl.id in keep
        if home.selectedLevel and home.selectedLevel not in keep:
            home.selectedLevel = next(iter(keep))
    else:
        keep = {lvl.id for lvl in home.levels}

    if hide_ceilings:
        for r in home.rooms:
            if r.level in keep:
                r.ceilingVisible = False

    tmp = tempfile.NamedTemporaryFile(
        suffix=".sh3d", prefix="sh3d-render-", delete=False,
    )
    tmp.close()
    try:
        save_home(home, tmp.name, copy_content_from=home_path)
        yield tmp.name
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


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
        return  # already up to date — javac isn't needed in this run

    # Only resolve javac when there's actually something to compile. The
    # bundled SH3D JRE has no javac, so users without a JDK can still run
    # renders against an already-cached classes dir.
    javac = _find_javac()
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

def _strip_obj_commas(obj_path: Path) -> None:
    """BUG 1 safety net: strip thousands-separator commas from v/vn/vt lines.

    SH3D's OBJWriter uses NumberFormat.getNumberInstance(Locale.US) which
    enables grouping → values ≥1000 get comma separators (e.g.
    ``1,350.1787``). Blender's OBJ importer uses strtod which stops at the
    comma, collapsing far-side vertices. The Java-side fix in ExportObj
    handles this, but this Python pass is a last-resort guard against
    stale cached .class files or reflection failures.
    """
    if not obj_path.exists():
        return
    lines = obj_path.read_text().splitlines(keepends=True)
    changed = False
    fixed = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped and stripped[0] == "v" and len(stripped) > 1 and stripped[1] in (" ", "n", "t"):
            new_line = _remove_thousands_commas(stripped)
            if new_line != stripped:
                changed = True
            fixed.append(new_line + "\n")
        else:
            fixed.append(line)
    if changed:
        obj_path.write_text("".join(fixed))


def _remove_thousands_commas(s: str) -> str:
    """Remove commas that sit between digits (thousands separators)."""
    result = []
    for i, ch in enumerate(s):
        if ch == ",":
            prev_digit = i > 0 and s[i - 1].isdigit()
            next_digit = i + 1 < len(s) and s[i + 1].isdigit()
            if prev_digit and next_digit:
                continue
        result.append(ch)
    return "".join(result)


def _needs_export_preprocessing(home_path: str) -> bool:
    """Quick XML scan: does the .sh3d have a non-zero environment.wallsAlpha?

    When wallsAlpha > 0, OBJWriter sets d=(1-alpha) on EVERY material (not
    just walls), making all surfaces partially transparent. Cycles renders
    this as stacked alpha-blended layers — walls look broken when you can
    see through them into other walls.
    """
    import re
    import zipfile

    try:
        with zipfile.ZipFile(home_path) as z:
            if "Home.xml" not in z.namelist():
                return False
            xml = z.read("Home.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, OSError):
        return False
    # Non-zero wallsAlpha on environment
    env_match = re.search(r'<environment\b[^>]*>', xml)
    if env_match:
        alpha_match = re.search(r'wallsAlpha="([^"]+)"', env_match.group(0))
        if alpha_match:
            try:
                if float(alpha_match.group(1)) > 0:
                    return True
            except ValueError:
                pass
    return False


def _copy_with_walls_alpha_zeroed(src_path: str, dst_path: str) -> None:
    """Copy `src_path` to `dst_path` with `wallsAlpha` zeroed.

    Only zeroes wallsAlpha — level visibility is left as-is because
    filtered_levels has already set it correctly for the render request.
    The mutation lives only on disk in the temp copy; the user's
    source .sh3d is never touched.
    """
    from cli_anything.sweethome3d.core.session import Session

    sess = Session.open(src_path)
    sess.home.environment.wallsAlpha = 0
    sess.save(dst_path)


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
    view: str = "camera",
    exclude_levels: Optional[list[str]] = None,
    include_levels: Optional[list[str]] = None,
    hide_ceilings: bool = False,
) -> dict:
    """OBJ export via ExportObj.java → Blender Cycles+OptiX render."""
    if view not in ("camera", "top", "iso"):
        raise ValueError(f"view must be camera, top, or iso; got {view!r}")
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

    # Zero wallsAlpha and ensure levels are correctly visible for export.
    # SH3D's OBJWriter emits d=(1-alpha) on EVERY material when
    # environment.wallsAlpha > 0, making all surfaces ~7.5% transparent
    # (wallsAlpha=0.0745 → d=0.9255), which Cycles renders as broken
    # alpha-blended layers. Also, the GUI default of visible=false on
    # non-active levels means ExportObj would skip upper floors unless
    # we promote them — but filtered_levels may have already set some
    # to false deliberately. We zero wallsAlpha always, and leave level
    # visibility as-is (filtered_levels already set it correctly).
    export_src = home_path
    if _needs_export_preprocessing(home_path):
        temp_sh3d = work / "preprocessed.sh3d"
        _copy_with_walls_alpha_zeroed(home_path, str(temp_sh3d))
        export_src = str(temp_sh3d)

    # Apply level filters / ceiling hiding for this render only.
    with filtered_levels(
        export_src,
        include=include_levels,
        exclude=exclude_levels,
        hide_ceilings=hide_ceilings,
    ) as filtered_src:
        _run_java_export_obj(sh3d_home, _classes_dir, filtered_src, obj_path)

    # BUG 1 safety net: strip any remaining thousands-separator commas
    # from the OBJ file. The Java-side fix (reflection + post-process)
    # should handle this, but this Python-side pass is a last-resort
    # guard in case the Java fix is incomplete or the cached .class is
    # stale.
    _strip_obj_commas(obj_path)

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
    if view != "camera":
        cmd += ["--view", view]

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
        "view": view,
        "levels_excluded": exclude_levels,
        "levels_included": include_levels,
        "ceilings_hidden": hide_ceilings,
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
    samples: int = 256,                # gpu_photo only
    timeout_s: int = 600,
    view: str = "camera",              # gpu_photo only
    exclude_levels: Optional[list[str]] = None,   # gpu_photo only
    include_levels: Optional[list[str]] = None,   # gpu_photo only
    hide_ceilings: bool = False,                   # gpu_photo only
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
            view=view,
            exclude_levels=exclude_levels,
            include_levels=include_levels,
            hide_ceilings=hide_ceilings,
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
