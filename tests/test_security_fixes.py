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
