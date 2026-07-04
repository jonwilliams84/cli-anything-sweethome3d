# cli-anything-sweethome3d

A Designer API + CLI for [SweetHome 3D](https://www.sweethome3d.com/) — build
`.sh3d` floor-plans programmatically from Python or from a declarative JSON
spec. Part of the `cli-anything-*` family of LLM-ergonomic harnesses: it favours
introspection, validation, and spec round-trip so an agent can design a home,
inspect what it built, and re-serialise it deterministically.

## What it does

- **Build floor-plans in code** — walls, rooms, levels, doors/windows and
  furniture placed via the `designer` core API (centimetre coordinate space).
- **Spec round-trip** — describe a home as JSON (`spec_version`, levels, walls,
  rooms, furniture), materialise it to a real `.sh3d`, and read it back.
- **Render previews** — export a PNG of the plan via the `renderer` (optional
  `Pillow` for higher-quality output).
- **Validation & introspection** — the spec is validated before it touches the
  filesystem, and the model can query the catalogue / current design.

## Install

```bash
pip install -e .              # core is pure stdlib
pip install -e '.[render]'    # + Pillow for nicer PNG renders
pip install -e '.[dev]'       # + pytest / pytest-cov
```

Exposes the `cli-anything-sweethome3d` console script.

## Quick start

```bash
# Build the bundled example (UK 4-bed semi) from its JSON spec
python examples/uk_4bed_designer.py
```

See `examples/uk_4bed_spec.json` for the spec format and
`examples/uk_4bed_designer.py` for the programmatic API.

## Layout

- `cli_anything/sweethome3d/core/designer.py` — the Designer API (build/edit a plan).
- `cli_anything/sweethome3d/core/renderer.py` — plan → PNG rendering.
- `cli_anything/sweethome3d/core/__main__.py` — CLI entry point.
- `cli_anything/sweethome3d/skills/` — packaged agent skill docs (furniture
  catalogue, spec reference).
- `examples/` — worked example spec + generated `.sh3d`/`.png`.
- `tests/` — unit tests.

## Testing

```bash
python -m pytest
```

## Licence

MIT — see [LICENSE](LICENSE).
