"""Regression test: cubicasa_runner.py must sanitise its argv inputs.

Ensures that no unsanitised path reaches file operations or any subprocess
context.  The _sanitise_path function rejects None, null bytes, and shell
metacharacters / control characters that could enable injection.
"""
import importlib
import pytest


@pytest.fixture
def runner():
    """Import cubicasa_runner without triggering its heavy torch imports.

    The module-level code only imports os/sys/json/re — the torch/PIL imports
    happen inside main(), so importing the module is safe even without torch.
    """
    return importlib.import_module("cli_anything.sweethome3d.tools.cubicasa_runner")


# ---------------------------------------------------------------------------
# _sanitise_path unit tests
# ---------------------------------------------------------------------------

class TestSanitisePath:
    def test_accepts_normal_path(self, runner):
        assert runner._sanitise_path("/tmp/safe.png") == "/tmp/safe.png"

    def test_accepts_relative_path(self, runner):
        assert runner._sanitise_path("input.png") == "input.png"

    def test_accepts_path_with_spaces(self, runner):
        assert runner._sanitise_path("/tmp/my file.png") == "/tmp/my file.png"

    def test_rejects_none(self, runner):
        with pytest.raises(ValueError, match="must not be None"):
            runner._sanitise_path(None)

    def test_rejects_null_byte(self, runner):
        with pytest.raises(ValueError, match="null byte"):
            runner._sanitise_path("safe\x00evil.png")

    def test_rejects_shell_pipe(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png | rm -rf /")

    def test_rejects_shell_semicolon(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png; rm -rf /")

    def test_rejects_shell_backtick(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png`whoami`")

    def test_rejects_shell_dollar(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png$(whoami)")

    def test_rejects_shell_ampersand(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png & whoami")

    def test_rejects_newline(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png\nrm -rf /")

    def test_rejects_angle_bracket(self, runner):
        with pytest.raises(ValueError, match="unsafe characters"):
            runner._sanitise_path("foo.png > /etc/passwd")


# ---------------------------------------------------------------------------
# main() integration — sanitisation happens before any file / torch access
# ---------------------------------------------------------------------------

class TestMainSanitisesInputs:
    def test_main_rejects_malicious_inp(self, runner, monkeypatch):
        """main() must reject a malicious input path before touching files."""
        # Even if CUBICASA_HOME is set, the sanitisation must fire first.
        monkeypatch.setenv("CUBICASA_HOME", "/nonexistent")
        with pytest.raises(ValueError, match="unsafe characters"):
            runner.main("evil.png; rm -rf /", "/tmp/out.json")

    def test_main_rejects_malicious_out(self, runner, monkeypatch):
        """main() must reject a malicious output path before touching files."""
        monkeypatch.setenv("CUBICASA_HOME", "/nonexistent")
        with pytest.raises(ValueError, match="unsafe characters"):
            runner.main("/tmp/safe.png", "out.json | cat /etc/passwd")

    def test_main_rejects_null_byte_inp(self, runner, monkeypatch):
        monkeypatch.setenv("CUBICASA_HOME", "/nonexistent")
        with pytest.raises(ValueError, match="null byte"):
            runner.main("safe\x00evil.png", "/tmp/out.json")

    def test_main_rejects_none_inp(self, runner, monkeypatch):
        monkeypatch.setenv("CUBICASA_HOME", "/nonexistent")
        with pytest.raises(ValueError, match="must not be None"):
            runner.main(None, "/tmp/out.json")
