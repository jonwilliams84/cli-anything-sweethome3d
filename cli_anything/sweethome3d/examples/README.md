# SweetHome3D SVG Import Examples

## bungalow-spec.yaml

A complete specification for converting architectural floor plans (SVG format) into SweetHome3D models. This example demonstrates all configurable sections.

### Quick Start

Place your floor plan SVGs in the same directory as this spec, then import:

```python
from cli_anything.sweethome3d.core.svg_import import svg_to_home_multi
svg_to_home_multi(spec="cli_anything/sweethome3d/examples/bungalow-spec.yaml")
```

### Spec Sections

- **meta**: Home name, output file, units
- **input**: SVG floor plan files and level names
- **alignment**: Green marker alignment across floors
- **walls**: Wall thickness, colors, textures, extraction rules
- **openings**: Doors, windows, skylights by color
- **lights**: Pendant lamps and fixtures
- **rooms**: Floor/ceiling colors per level and room name
- **environment**: Sky, ground, and wall transparency
- **levels**: Floor slab thickness and vertical spacing

Every leaf value is optional. Unspecified values use defaults from `_DEFAULT_SPEC` in `core/svg_import.py`.
