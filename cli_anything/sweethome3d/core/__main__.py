"""CLI entry point: python3 -m cli_anything.sweethome3d.core.designer

Usage
-----
Run a spec JSON file produced by Designer.to_spec() through to .sh3d + render:

    python3 -m cli_anything.sweethome3d.core.designer \\
        --spec design.json \\
        --out  Home.sh3d  \\
        --render Home.png

Options
-------
--spec   PATH   Input JSON spec (from Designer.to_spec() / examples/*.json)
--out    PATH   Output .sh3d file (default: Home.sh3d)
--render PATH   Output PNG floor-plan render (optional)
--validate      Print validate() report and exit (no file written)
--describe      Print describe() state and exit (no file written)

This entry point is the final step in the LLM → spec → .sh3d pipeline:

    1. User prompt → LLM generates spec JSON (or Python using the API)
    2. python3 -m cli_anything.sweethome3d.core.designer --spec spec.json --out Home.sh3d
    3. SweetHome3D opens Home.sh3d for full 3-D view / rendering
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m cli_anything.sweethome3d.core.designer",
        description="SweetHome3D Designer CLI — build .sh3d homes from JSON specs.",
    )
    parser.add_argument("--spec", metavar="PATH",
                        help="Input spec JSON file (from Designer.to_spec())")
    parser.add_argument("--out", metavar="PATH", default="Home.sh3d",
                        help="Output .sh3d file (default: Home.sh3d)")
    parser.add_argument("--render", metavar="PATH", default=None,
                        help="Output PNG floor-plan render path (optional)")
    parser.add_argument("--validate", action="store_true",
                        help="Print validate() report and exit without writing files")
    parser.add_argument("--describe", action="store_true",
                        help="Print describe() state and exit without writing files")

    args = parser.parse_args(argv)

    # Import here so the module is importable even before install
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))))

    from cli_anything.sweethome3d.core.designer import Designer

    if args.spec is None:
        parser.error("--spec is required. Provide a JSON file from Designer.to_spec().")

    spec_path = Path(args.spec)
    if not spec_path.exists():
        sys.exit(f"Error: spec file not found: {spec_path}")

    try:
        with spec_path.open(encoding="utf-8") as fh:
            spec = json.load(fh)
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: invalid JSON in {spec_path}: {exc}")

    try:
        d = Designer.from_spec(spec)
    except Exception as exc:
        sys.exit(f"Error: failed to load spec: {exc}")

    if args.validate:
        report = d.validate()
        print(json.dumps(report, indent=2))
        # Exit 1 if there are critical issues
        issues = (
            any(not ok for ok in report["envelope_closed"])
            or bool(report["orphan_endpoints"])
        )
        sys.exit(1 if issues else 0)

    if args.describe:
        state = d.describe()
        print(json.dumps(state, indent=2))
        sys.exit(0)

    out_path = Path(args.out)
    try:
        written = d.save(out_path, render_png=args.render)
        print(f"Written: {written}")
        if args.render:
            print(f"Render:  {args.render}")
    except Exception as exc:
        sys.exit(f"Error writing output: {exc}")


if __name__ == "__main__":
    main()
