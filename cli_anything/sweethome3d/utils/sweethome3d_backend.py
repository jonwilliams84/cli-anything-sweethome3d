"""Sweet Home 3D backend — invokes the real GUI binary for photo render.

Sweet Home 3D has no built-in headless render mode. We work around this by:
  1. Locating the `sweethome3d` binary or its executable JAR
  2. Invoking it with `-open <file>` (the only CLI flag it supports)

For real photo render in v1.0.0, the harness simply ensures the binary is
installable and provides a `render` command that opens the project in SH3D.
True headless render is a v1.1 goal once we ship a Java render helper JAR.

Locate order:
  1. $SWEETHOME3D_BIN
  2. `which sweethome3d`
  3. /Applications/Sweet Home 3D.app/Contents/MacOS/SweetHome3D  (macOS)
  4. /opt/sweethome3d/SweetHome3D  (linux install)
  5. java -jar <SWEETHOME3D_JAR>  (if $SWEETHOME3D_JAR set)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


class Sweethome3DNotInstalled(RuntimeError):
    """Raised when the Sweet Home 3D binary cannot be found."""


def find_sweethome3d() -> list[str]:
    """Return an argv prefix suitable for invoking Sweet Home 3D.

    Caller appends ['-open', 'path.sh3d'] and runs subprocess.
    """
    if (env := os.environ.get("SWEETHOME3D_BIN")):
        if os.path.isfile(env):
            return [env]
    path = shutil.which("sweethome3d") or shutil.which("SweetHome3D")
    if path:
        return [path]
    macos = "/Applications/Sweet Home 3D.app/Contents/MacOS/SweetHome3D"
    if os.path.isfile(macos):
        return [macos]
    for candidate in ("/opt/sweethome3d/SweetHome3D",
                       "/usr/share/sweethome3d/SweetHome3D"):
        if os.path.isfile(candidate):
            return [candidate]
    if (jar := os.environ.get("SWEETHOME3D_JAR")):
        if os.path.isfile(jar):
            java = shutil.which("java")
            if not java:
                raise Sweethome3DNotInstalled(
                    "SWEETHOME3D_JAR is set but no `java` binary found in PATH"
                )
            return [java, "-jar", jar]
    raise Sweethome3DNotInstalled(
        "Sweet Home 3D is not installed. Install it from:\n"
        "  https://www.sweethome3d.com/download.jsp\n"
        "Or set one of the following environment variables:\n"
        "  SWEETHOME3D_BIN — path to the SweetHome3D binary\n"
        "  SWEETHOME3D_JAR — path to the SweetHome3D-7.x.jar (will use `java -jar`)\n"
    )


def open_in_app(sh3d_path: str, *, wait: bool = False,
                  timeout: Optional[float] = None) -> int:
    """Launch SH3D with the given file open. Returns exit code (or pid if !wait).

    SH3D is GUI-only — this will pop a window unless run with a virtual display.
    """
    argv = find_sweethome3d() + ["-open", os.path.abspath(sh3d_path)]
    if wait:
        proc = subprocess.run(argv, timeout=timeout)
        return proc.returncode
    proc = subprocess.Popen(argv,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    return proc.pid


def version() -> Optional[str]:
    """Best-effort version probe by reading the JAR filename or `--version`.

    SH3D's binary does not accept `--version`; we read the JAR filename if one
    was used to find it.
    """
    argv = find_sweethome3d()
    for token in argv:
        # match "SweetHome3D-7.5.jar" or similar
        if "SweetHome3D-" in token and token.endswith(".jar"):
            try:
                # SweetHome3D-7.5.jar → "7.5"
                base = os.path.basename(token)
                inner = base[len("SweetHome3D-"):-len(".jar")]
                return inner
            except Exception:
                pass
    return None
