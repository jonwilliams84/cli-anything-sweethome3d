"""Regression tests for cubicasa_runner input sanitisation.

The cubicasa_runner script accepts file paths via sys.argv and environment
variables. These paths must be sanitised before use so that shell
metacharacters can never break out of the intended argument slot — even
though the script itself does not invoke a shell, it may be launched *through*
a shell by pdf_import.run_model or by a user, so defence-in-depth is required.
"""
import os
import sys
import pytest

# Ensure the package is importable when running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cli_anything.sweethome3d.tools.cubicasa_runner import _sanitize_path


# ---- _sanitize_path: reject dangerous inputs ---------------------------------

@pytest.mark.parametrize("bad_path", [
    "foo;rm -rf /",
    "foo$(whoami)",
    "foo`whoami`",
    "foo|cat",
    "foo&bar",
    "foo>bar",
    "foo<bar",
    "foo\nbar",
    "foo\rbar",
    "foo\\bar",
    "foo$bar",
    "foo\x00bar",
    "",
])
def test_sanitize_path_rejects_shell_metachars(bad_path):
    """Paths containing shell metacharacters or NUL must be rejected."""
    with pytest.raises(ValueError):
        _sanitize_path(bad_path, "input")


def test_sanitize_path_rejects_empty_output():
    with pytest.raises(ValueError):
        _sanitize_path("", "output")


# ---- _sanitize_path: accept legitimate paths ---------------------------------

@pytest.mark.parametrize("good_path", [
    "/tmp/plan.png",
    "my plan.png",
    "résultat.json",
    "./output/dir/file.json",
    "plan_with-dots.and-extensions.png",
])
def test_sanitize_path_accepts_normal_paths(good_path):
    """Normal file paths (spaces, unicode, dots, hyphens) must pass."""
    assert _sanitize_path(good_path, "input") == good_path


# ---- main() rejects unsanitised argv before touching the filesystem -----------

def test_main_rejects_injection_in_input():
    """main() must raise ValueError for a shell-injection input path before
    it ever checks CUBICASA_HOME or opens a file."""
    with pytest.raises(ValueError):
        from cli_anything.sweethome3d.tools.cubicasa_runner import main
        main("foo;rm -rf /", "safe.json")


def test_main_rejects_injection_in_output():
    with pytest.raises(ValueError):
        from cli_anything.sweethome3d.tools.cubicasa_runner import main
        main("safe.png", "out;rm -rf /")


def test_main_rejects_empty_paths():
    with pytest.raises(ValueError):
        from cli_anything.sweethome3d.tools.cubicasa_runner import main
        main("", "out.json")
    with pytest.raises(ValueError):
        from cli_anything.sweethome3d.tools.cubicasa_runner import main
        main("in.png", "")
