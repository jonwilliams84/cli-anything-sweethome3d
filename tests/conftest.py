"""Root-level test configuration.

Ensures the ``cli_anything`` package is importable when running
``pytest tests/`` from the repository root, and also makes the
existing test-suite under ``cli_anything/sweethome3d/tests`` discoverable.
"""
import os
import sys

# Make the repo root importable so `cli_anything.*` resolves.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Collect tests from the package's own test directory as well.
collect_ignore_glob = []
