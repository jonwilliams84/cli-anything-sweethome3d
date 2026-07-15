"""Regression tests — input sanitisation in cubicasa_runner.

The cubicasa_runner module receives filesystem paths from sys.argv (inp, out)
and environment variables (CUBICASA_HOME, CUBICASA_WEIGHTS).  These must be
sanitised before use in any file operation or subprocess argument to prevent
injection of shell/argv-breaking characters (null bytes, newlines, etc.).

These tests exercise the ``_sanitise_path`` helper directly and verify that
``main`` rejects unsafe inputs before reaching any model/file code.
"""
import os
import sys
import importlib

import pytest

# Import the module under test
from cli_anything.sweethome3d.tools import cubicasa_runner as cr


# ---------------------------------------------------------------------------
# _sanitise_path unit tests
# ---------------------------------------------------------------------------
class TestSanitisePath:
    def test_accepts_normal_path(self):
        assert cr._sanitise_path("/tmp/safe.png") == "/tmp/safe.png"

    def test_accepts_normal_path_with_spaces(self):
        assert cr._sanitise_path("/tmp/my plan.png") == "/tmp/my plan.png"

    def test_rejects_none(self):
        with pytest.raises(ValueError, match="None"):
            cr._sanitise_path(None)

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            cr._sanitise_path("")

    def test_rejects_null_byte(self):
        with pytest.raises(ValueError, match="unsafe"):
            cr._sanitise_path("evil\x00.png")

    def test_rejects_newline(self):
        with pytest.raises(ValueError, match="unsafe"):
            cr._sanitise_path("evil\n.png")

    def test_rejects_carriage_return(self):
        with pytest.raises(ValueError, match="unsafe"):
            cr._sanitise_path("evil\r.png")

    def test_must_exist_rejects_missing_file(self):
        with pytest.raises(ValueError, match="does not exist"):
            cr._sanitise_path("/nonexistent/path/file.png", must_exist=True)

    def test_must_exist_accepts_existing_file(self, tmp_path):
        p = tmp_path / "real.png"
        p.write_bytes(b"data")
        assert cr._sanitise_path(str(p), must_exist=True) == str(p)


# ---------------------------------------------------------------------------
# main() integration tests — verify unsafe inputs are rejected early
# ---------------------------------------------------------------------------
class TestMainRejectsUnsafeInput:
    """main() must sanitise inp/out before any model or file operation.
    We set CUBICASA_HOME to a real dir so the check passes that far, then
    verify that bad inp/out paths raise ValueError before torch is imported."""

    def test_main_rejects_null_byte_in_inp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
        with pytest.raises(ValueError, match="unsafe"):
            cr.main("evil\x00.png", str(tmp_path / "out.json"))

    def test_main_rejects_newline_in_out(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
        # inp must exist — create a dummy file
        inp = tmp_path / "in.png"
        inp.write_bytes(b"data")
        with pytest.raises(ValueError, match="unsafe"):
            cr.main(str(inp), "out\n.json")

    def test_main_rejects_nonexistent_inp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
        with pytest.raises(ValueError, match="does not exist"):
            cr.main(str(tmp_path / "missing.png"), str(tmp_path / "out.json"))

    def test_main_rejects_null_byte_in_home(self, tmp_path, monkeypatch):
        """CUBICASA_HOME with null byte must be caught after the isdir check
        (a path with null bytes can't be a real dir, so the isdir guard fires
        first — but if somehow it passed, _sanitise_path would still catch it)."""
        # A path with \x00 can never be a valid directory, so main exits via
        # the isdir check.  We verify the sanitiser independently:
        with pytest.raises(ValueError, match="unsafe"):
            cr._sanitise_path("evil\x00/home")


# ---------------------------------------------------------------------------
# CLI entry point test — argv paths are sanitised
# ---------------------------------------------------------------------------
class TestCliEntryPoint:
    def test_argv_null_byte_rejected(self, tmp_path, monkeypatch):
        """When run as a script, unsafe argv paths must be rejected."""
        monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["cubicasa_runner.py", "evil\x00.png", "out.json"])
        with pytest.raises(ValueError, match="unsafe"):
            cr.main(sys.argv[1], sys.argv[2])
