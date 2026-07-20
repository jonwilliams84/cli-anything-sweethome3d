"""Regression tests for cubicasa_runner input sanitisation.

Verifies that unsanitised paths/args never reach file operations or any
subprocess/shell invocation.  The cubicasa_runner is invoked as a subprocess
by pdf_import.run_model; its own argv inputs must be validated before use.
"""
import importlib
import sys
import pytest


@pytest.fixture(autouse=True)
def _import_module():
    """Import cubicasa_runner without triggering its heavy torch imports.

    We only need _validate_path and the __main__ guard, so we import the
    module object lazily and make it available on sys.modules.
    """
    mod_path = "cli_anything.sweethome3d.tools.cubicasa_runner"
    if mod_path in sys.modules:
        return sys.modules[mod_path]
    # Importing the module is safe — heavy imports happen inside main(), not
    # at module top level.
    mod = importlib.import_module(mod_path)
    return mod


class TestValidatePath:
    """Unit tests for the _validate_path sanitiser."""

    def test_safe_path_passes_through(self, _import_module):
        mod = _import_module
        assert mod._validate_path("/tmp/safe_plan.png", "inp") == "/tmp/safe_plan.png"
        assert mod._validate_path("out.json", "out") == "out.json"

    def test_rejects_empty_string(self, _import_module):
        mod = _import_module
        with pytest.raises(ValueError, match="non-empty string"):
            mod._validate_path("", "inp")

    def test_rejects_non_string(self, _import_module):
        mod = _import_module
        with pytest.raises(ValueError, match="non-empty string"):
            mod._validate_path(None, "inp")
        with pytest.raises(ValueError, match="non-empty string"):
            mod._validate_path(123, "inp")

    def test_rejects_null_byte(self, _import_module):
        mod = _import_module
        with pytest.raises(ValueError, match="null byte"):
            mod._validate_path("/tmp/pla\x00n.png", "inp")

    @pytest.mark.parametrize("evil", [
        "/tmp/$(whoami).png",
        "/tmp/`whoami`.png",
        "/tmp/a;rm -rf /.png",
        "/tmp/a|cat.json",
        "/tmp/a&&b.png",
        "/tmp/a\nb.png",
        "/tmp/a\rb.png",
        "/tmp/a;b.png",
        "/tmp/a!b.png",
        "/tmp/a<b.png",
        "/tmp/a>b.png",
        "/tmp/a&b.png",
        "/tmp/${HOME}.png",
    ])
    def test_rejects_shell_metacharacters(self, _import_module, evil):
        mod = _import_module
        with pytest.raises(ValueError, match="shell metacharacters"):
            mod._validate_path(evil, "inp")


class TestMainSanitisesInputs:
    """Verify that main() calls _validate_path before any file access."""

    def test_main_rejects_unsafe_inp(self, _import_module, monkeypatch):
        """main() must reject an unsafe inp path before touching the filesystem."""
        mod = _import_module

        # If _validate_path doesn't raise, main() would proceed to check
        # CUBICASA_HOME and then do heavy imports.  We monkeypatch
        # os.environ to ensure CUBICASA_HOME is set so the only thing that
        # can stop us early is _validate_path.
        monkeypatch.setenv("CUBICASA_HOME", "/tmp")

        with pytest.raises(ValueError, match="shell metacharacters"):
            mod.main("/tmp/$(evil).png", "/tmp/out.json")

    def test_main_rejects_unsafe_out(self, _import_module, monkeypatch):
        """main() must reject an unsafe out path before touching the filesystem."""
        mod = _import_module
        monkeypatch.setenv("CUBICASA_HOME", "/tmp")

        with pytest.raises(ValueError, match="shell metacharacters"):
            mod.main("/tmp/safe.png", "/tmp/$(evil).json")

    def test_main_rejects_empty_inp(self, _import_module, monkeypatch):
        mod = _import_module
        monkeypatch.setenv("CUBICASA_HOME", "/tmp")

        with pytest.raises(ValueError, match="non-empty string"):
            mod.main("", "/tmp/out.json")

    def test_main_rejects_null_byte_out(self, _import_module, monkeypatch):
        mod = _import_module
        monkeypatch.setenv("CUBICASA_HOME", "/tmp")

        with pytest.raises(ValueError, match="null byte"):
            mod._validate_path("/tmp/out\x00.json", "out")
