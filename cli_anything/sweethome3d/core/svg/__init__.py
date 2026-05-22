"""SVG → SH3D Home importer, split by concern.

Public surface:
    svg_to_home          single-SVG legacy entry point
    svg_to_home_multi    spec-driven multi-SVG (one per floor)
    load_spec            YAML/JSON/dict spec resolver
"""

from cli_anything.sweethome3d.core.svg.pipeline import (
    svg_to_home,
    svg_to_home_multi,
)
from cli_anything.sweethome3d.core.svg.spec import load_spec

__all__ = ["svg_to_home", "svg_to_home_multi", "load_spec"]
