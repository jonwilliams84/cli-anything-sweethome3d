"""Regression tests for the top-3 automated security-scanner findings.

Covers:
  * B314 — xml.etree.ElementTree.parse on untrusted XML in
    cli_anything/sweethome3d/core/project.py and
    cli_anything/sweethome3d/core/svg/pipeline.py (must use defusedxml).
  * B108 — insecure hardcoded /tmp path in
    cli_anything/sweethome3d/core/render_runtime.py (must use a per-user
    XDG cache dir, not world-writable /tmp).
"""
import os
import re
import sys
import inspect
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# B314 — defusedxml must be used instead of xml.etree.ElementTree.parse
# ---------------------------------------------------------------------------

_BARE_ET_PARSE = re.compile(r"(?<![A-Za-z])ET\.parse\(")


def test_pipeline_svg_to_home_uses_defusedxml():
    """svg_to_home must parse via defusedxml, not bare xml.etree."""
    from cli_anything.sweethome3d.core.svg import pipeline

    src = inspect.getsource(pipeline.svg_to_home)
    assert "DefusedET.parse" in src
    assert not _BARE_ET_PARSE.search(src)


def test_project_load_uses_defusedxml():
    """project module must parse via defusedxml, not bare xml.etree."""
    from cli_anything.sweethome3d.core import project

    src = inspect.getsource(project)
    assert "DefusedET.parse" in src
    assert not _BARE_ET_PARSE.search(src)


def test_pipeline_rejects_billion_laughs():
    """defusedxml must reject the billion-laughs entity-expansion attack."""
    from cli_anything.sweethome3d.core.svg import pipeline

    bomb = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz ['
        '<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        ']>'
        '<svg xmlns="http://www.w3.org/2000/svg"><rect d="&lol3;"/></svg>'
    )
    with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
        f.write(bomb)
        path = f.name
    try:
        with pytest.raises(Exception):
            pipeline.svg_to_home(path)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# B108 — no hardcoded /tmp path for the bundled JDK
# ---------------------------------------------------------------------------

def test_find_javac_no_hardcoded_tmp():
    """_find_javac must not reference a world-writable /tmp path directly."""
    from cli_anything.sweethome3d.core import render_runtime

    src = inspect.getsource(render_runtime._find_javac)
    assert '"/tmp/jdk8u402-b06' not in src
    assert "_cache_dir()" in src


def test_find_javac_bundled_path_under_cache_dir():
    """The bundled-jdk candidate path must live under the XDG cache dir."""
    from cli_anything.sweethome3d.core import render_runtime

    cache = render_runtime._cache_dir()
    candidate = cache / "jdk8u402-b06" / "bin" / "javac"
    assert "/tmp" not in str(candidate)
    assert str(cache) in str(candidate)


# ---------------------------------------------------------------------------
# B404 / B603 — shell-metacharacter guard in run_model (pdf_import.py)
# ---------------------------------------------------------------------------

def test_run_model_rejects_shell_metacharacters():
    """run_model must refuse command tokens containing shell metacharacters."""
    from cli_anything.sweethome3d.core.pdf_import import (
        _validate_shell_safe,
    )

    dangerous = [
        "python; echo pwned",
        "python && echo pwned",
        "python | cat",
        "$(whoami)",
        "`id`",
        "python>out.txt",
        "python<in.txt",
        "python!x",
        "python$x",
        "python'name",
        'python"name',
    ]
    for token in dangerous:
        with pytest.raises(ValueError, match="metacharacter"):
            _validate_shell_safe(token, "token")

    # Safe paths with normal characters must pass
    safe = [
        "/usr/bin/python3",
        "/home/user/scripts/my-model.py",
        "/tmp/output.json",
    ]
    for token in safe:
        _validate_shell_safe(token, "token")  # must not raise


def test_run_model_validates_paths_for_metacharacters(tmp_path):
    """run_model must reject paths containing shell metacharacters."""
    from cli_anything.sweethome3d.core.pdf_import import (
        _validate_shell_safe,
    )

    dangerous_paths = [
        "/tmp/p lan.png",          # space
        "/tmp/$(whoami).png",      # command substitution
        "/tmp/a`id`b.png",         # backtick substitution
        "/tmp/f;echo.sh",          # command chaining
    ]
    for path in dangerous_paths:
        with pytest.raises(ValueError, match="metacharacter"):
            _validate_shell_safe(path, "png_path")


def test_run_model_validates_post_substitution_tokens(tmp_path):
    """After {in}/{out} substitution the final argv must also be validated."""
    from cli_anything.sweethome3d.core.pdf_import import (
        _validate_shell_safe,
    )

    # Simulate: user writes a template like "python {in}; echo pwned" (broken template)
    # After substitution, the whole thing is one token so shlex.split won't split it,
    # but _validate_shell_safe catches the ";" before subprocess is called.
    dangerous_template = ["python {in}; echo pwned"]
    png = str(tmp_path / "plan.png")
    out = str(tmp_path / "out.json")

    with pytest.raises(ValueError, match="metacharacter"):
        for token in dangerous_template:
            _validate_shell_safe(token.replace("{in}", png), "substituted token")


def test_run_model_validates_input_file_exists(tmp_path):
    """run_model must refuse to run if the input PNG does not exist."""
    from cli_anything.sweethome3d.core.pdf_import import run_model

    png = tmp_path / "does-not-exist.png"
    out = tmp_path / "out.json"

    with pytest.raises(FileNotFoundError):
        run_model(str(png), str(out), model_cmd=["echo", "unused"])


# ---------------------------------------------------------------------------
# B405 — align.py must use defusedxml, not xml.etree.ElementTree
# ---------------------------------------------------------------------------

def test_align_uses_defusedxml_not_stdlib_et():
    """align.py must import defusedxml.ElementTree, not xml.etree.ElementTree."""
    import cli_anything.sweethome3d.core.svg.align as align

    src = inspect.getsource(align)
    # Must NOT import the vulnerable stdlib module
    assert "import xml.etree.ElementTree" not in src
    # Must use defusedxml
    assert "defusedxml" in src


def test_align_fromstring_rejects_entity_expansion():
    """ET.fromstring in align.py (now defusedxml) must reject entity bombs."""
    from cli_anything.sweethome3d.core.svg import align

    bomb = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz ['
        '<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        ']>'
        '<e>&lol3;</e>'
    )
    # defusedxml raises EntitiesForbidden / DTDForbidden
    with pytest.raises(Exception):
        align.ET.fromstring(bomb)


def test_align_extract_corner_markers_works_with_safe_svg():
    """extract_corner_markers must still parse safe SVG correctly after
    switching to defusedxml."""
    from cli_anything.sweethome3d.core.svg.align import extract_corner_markers

    safe_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect x="10" y="20" width="5" height="5" fill="#55d400"/>'
        '<rect x="100" y="200" width="5" height="5" fill="#55d400"/>'
        '<rect x="50" y="50" width="5" height="5" fill="#ff0000"/>'
        '</svg>'
    )
    from defusedxml import ElementTree as DefusedET
    from cli_anything.sweethome3d.core.svg.parse import strip_ns
    root = DefusedET.fromstring(safe_svg)
    strip_ns(root)
    markers = extract_corner_markers(root)
    # Only the two green rects should be detected
    assert len(markers) == 2
    # First marker bbox around (10,20)
    assert markers[0] == (10.0, 20.0, 15.0, 25.0)


# ---------------------------------------------------------------------------
# B603 — render_runtime.py subprocess calls must have validated nosec
# ---------------------------------------------------------------------------

def test_render_gpu_photo_has_nosec_b603():
    """_render_gpu_photo subprocess.run must carry a nosec B603 suppression
    with a concrete justification (cmd is a list, inputs whitelisted)."""
    from cli_anything.sweethome3d.core import render_runtime

    src = inspect.getsource(render_runtime._render_gpu_photo)
    # The subprocess.run call must have a nosec B603 comment
    assert "nosec B603" in src
    # The justification must cite the concrete validation: view whitelist
    assert "whitelisted" in src.lower() or "whitelist" in src.lower()


def test_render_gpu_photo_validates_view():
    """_render_gpu_photo must reject views outside the whitelist before
    the subprocess call (this is the concrete reason the nosec is safe)."""
    from cli_anything.sweethome3d.core import render_runtime

    with pytest.raises(ValueError, match="view must be camera, top, or iso"):
        render_runtime._render_gpu_photo(
            "/nonexistent/home.sh3d",
            "/nonexistent/out.png",
            samples=1,
            width=100,
            height=100,
            timeout_s=10,
            view="evil; rm -rf /",
        )


def test_render_cpu_photo_has_nosec_b603():
    """render() (cpu_photo engine) subprocess.run must carry a nosec B603
    suppression with a concrete justification."""
    from cli_anything.sweethome3d.core import render_runtime

    src = inspect.getsource(render_runtime.render)
    assert "nosec B603" in src
    # Justification must cite the engine/quality whitelist
    assert "whitelisted" in src.lower() or "whitelist" in src.lower()


def test_render_rejects_unknown_engine(monkeypatch):
    """render() must reject engines outside the whitelist before subprocess."""
    from cli_anything.sweethome3d.core import render_runtime

    # Bypass the SH3D home lookup / compilation so we reach the engine
    # whitelist check (the concrete reason the nosec B603 is safe).
    monkeypatch.setattr(render_runtime, "_find_sh3d_home", lambda: Path("/fake"))
    monkeypatch.setattr(render_runtime, "_compile", lambda *a, **k: None)
    monkeypatch.setattr(render_runtime, "_compiled", True)

    with pytest.raises(ValueError, match="Unknown engine"):
        render_runtime.render(
            "/nonexistent/home.sh3d",
            "/nonexistent/out.png",
            engine="evil_engine",
            width=100,
            height=100,
        )


def test_render_rejects_bad_quality(monkeypatch, tmp_path):
    """render() must reject quality values outside LOW/MEDIUM/HIGH."""
    from cli_anything.sweethome3d.core import render_runtime

    # Build a minimal fake SH3D home so the java_bin.exists() check
    # passes and we reach the quality whitelist check.
    (tmp_path / "runtime" / "bin").mkdir(parents=True)
    (tmp_path / "runtime" / "bin" / "java").write_text("#!/bin/sh\n")
    (tmp_path / "lib").mkdir()

    monkeypatch.setattr(render_runtime, "_find_sh3d_home", lambda: tmp_path)
    monkeypatch.setattr(render_runtime, "_compile", lambda *a, **k: None)
    monkeypatch.setattr(render_runtime, "_compiled", True)
    monkeypatch.setattr(render_runtime, "_classpath", lambda *a, **k: "fake")

    with pytest.raises(ValueError, match="quality must be LOW, MEDIUM, or HIGH"):
        render_runtime.render(
            "/nonexistent/home.sh3d",
            "/nonexistent/out.png",
            engine="cpu_photo",
            width=100,
            height=100,
            quality="evil; rm -rf /",
        )
