"""cli-anything-sweethome3d — Click CLI + REPL entry point.

Project state model:
  - One-shot mode: each command opens the .sh3d, mutates, auto-saves
  - REPL mode: project is loaded once, mutations stay in memory until save
"""

from __future__ import annotations

import json
import math
import os
import shlex
from typing import Any, Optional

import click

from cli_anything.sweethome3d import __version__
from cli_anything.sweethome3d.core import (
    annotations as ann_core,
    background_image as bg_core,
    cameras as cam_core,
    catalog as catalog_core,
    catalog_scan as catalog_scan_core,
    environment as env_core,
    validate as validate_core,
    export as export_core,
    find as find_core,
    furniture as furn_core,
    furniture_groups as group_core,
    levels as lvl_core,
    light_emitters as light_core,
    materials as mat_core,
    print_settings as print_core,
    project as proj_core,
    rooms as rooms_core,
    sashes as sash_core,
    shelves as shelf_core,
    textures as tex_core,
    walls as walls_core,
)
from cli_anything.sweethome3d.core.model import Baseboard, Camera
from cli_anything.sweethome3d.core.session import Session
from cli_anything.sweethome3d.core.svg_import import load_spec, svg_to_home_multi
from cli_anything.sweethome3d.utils import sweethome3d_backend as backend
from cli_anything.sweethome3d.utils.repl_skin import ReplSkin


# ─────────────────────────────────────────────────────── helpers


def _emit(ctx: click.Context, data: Any) -> None:
    """Print data in JSON mode if --json was passed, else human form."""
    if ctx.obj.get("json"):
        # convert dataclasses to dicts via __dict__ shallow; lists too
        def _conv(o):
            if hasattr(o, "__dict__"):
                d = {}
                for k, v in vars(o).items():
                    d[k] = _conv(v)
                return d
            if isinstance(o, list):
                return [_conv(x) for x in o]
            if isinstance(o, tuple):
                return [_conv(x) for x in o]
            return o
        click.echo(json.dumps(_conv(data), indent=2, default=str))
        return
    if isinstance(data, list):
        for row in data:
            if hasattr(row, "__dict__"):
                click.echo(_one_line(row))
            else:
                click.echo(row)
        return
    if hasattr(data, "__dict__"):
        for k, v in vars(data).items():
            click.echo(f"{k}: {v}")
        return
    if isinstance(data, dict):
        for k, v in data.items():
            click.echo(f"{k}: {v}")
        return
    click.echo(data)


def _one_line(obj) -> str:
    bits = []
    if hasattr(obj, "catalogId") and obj.catalogId and not hasattr(obj, "x"):
        # CatalogEntry — catalogId is the lookup key, surface it first
        bits.append(f"catalogId={obj.catalogId}")
    if hasattr(obj, "id") and obj.id:
        bits.append(f"id={obj.id}")
    if hasattr(obj, "name") and obj.name:
        bits.append(f"name={obj.name}")
    if hasattr(obj, "kind") and obj.kind:
        bits.append(f"kind={obj.kind}")
    if hasattr(obj, "category") and getattr(obj, "category", None):
        bits.append(f"category={obj.category}")
    if hasattr(obj, "x") and hasattr(obj, "y"):
        bits.append(f"x={obj.x:g},y={obj.y:g}")
    return f"<{type(obj).__name__} " + ", ".join(bits) + ">"


def _load_session(ctx: click.Context) -> Session:
    """Return the active session — open the file in --project or fail."""
    sess: Optional[Session] = ctx.obj.get("session")
    if sess is not None:
        return sess
    path = ctx.obj.get("project")
    if not path:
        raise click.UsageError(
            "no project loaded; pass --project <file.sh3d> or run inside REPL"
        )
    if not os.path.isfile(path):
        # allow auto-creation when path is given but doesn't exist
        sess = Session.new()
        sess.path = path
    else:
        sess = Session.open(path)
    ctx.obj["session"] = sess
    return sess


def _autosave(ctx: click.Context) -> None:
    """Save the session after a one-shot mutation, unless --dry-run or REPL."""
    if ctx.obj.get("in_repl"):
        return
    if ctx.obj.get("dry_run"):
        return
    sess: Optional[Session] = ctx.obj.get("session")
    if sess is None:
        return
    if not sess.modified:
        return
    if not sess.path:
        return
    sess.save()


def _parse_int_color(s: Optional[str]) -> Optional[int]:
    """Parse a color string like '#FFEE88' (RGB) or 'FFFFEE88' (ARGB) into an int.

    SH3D stores colours as ARGB. A 6-digit RGB input is taken as opaque
    (alpha=FF) — otherwise zero-alpha would silently kill light intensity
    for environment colours (sky/ground/light/ceilingLight).
    """
    if s is None:
        return None
    s = s.strip().lstrip("#")
    if not s:
        return None
    val = int(s, 16)
    if len(s) == 6:
        val |= 0xFF000000
    return val


def _json_flag(f):
    """Allow --json on any subcommand, not just the root.

    Root --json sets ctx.obj["json"] in `cli`. Per-subcommand --json updates
    ctx.obj["json"] before _emit runs — so users can put --json wherever it
    reads naturally.
    """
    def callback(ctx, _param, value):
        if value:
            ctx.ensure_object(dict)
            ctx.obj["json"] = True
        return value
    return click.option(
        "--json", "json_out_sub", is_flag=True, expose_value=False,
        is_eager=True, callback=callback,
        help="Emit machine-readable JSON output",
    )(f)


# ─────────────────────────────────────────────────────── root group

@click.group(invoke_without_command=True,
              context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", "-V", prog_name="cli-anything-sweethome3d")
@click.option("--project", "-p", type=click.Path(),
                help="Path to a .sh3d file (one-shot or REPL load target)")
@click.option("--json", "json_out", is_flag=True,
                help="Emit machine-readable JSON output")
@click.option("--dry-run", is_flag=True,
                help="Don't save changes (one-shot mode)")
@click.pass_context
def cli(ctx: click.Context, project: Optional[str], json_out: bool,
         dry_run: bool) -> None:
    """cli-anything-sweethome3d — Sweet Home 3D from the command line.

    Without a subcommand, drops into the interactive REPL. With a
    subcommand, performs the operation and auto-saves the project.

    Schema/version: SH3D 7.x (`<home version="7400">`).
    """
    ctx.ensure_object(dict)
    ctx.obj["project"] = project
    ctx.obj["json"] = json_out
    ctx.obj["dry_run"] = dry_run
    ctx.obj["in_repl"] = False
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl, project_path=project)


# ─────────────────────────────────────────────────────── project group

@cli.group()
def project():
    """Project: new, open, save, info."""


@project.command("new")
@click.option("--name", "-n", help="Home name")
@click.option("--output", "-o", type=click.Path(), required=True,
                help="Output .sh3d path")
@click.pass_context
def project_new(ctx, name, output):
    """Create a new empty .sh3d file."""
    sess = Session.new(name=name)
    sess.save(output)
    ctx.obj["session"] = sess
    _emit(ctx, {"created": output, "name": name, "version": sess.home.version})


@project.command("open")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def project_open(ctx, path):
    """Load a .sh3d file (REPL only — for one-shot use --project)."""
    sess = Session.open(path)
    ctx.obj["session"] = sess
    ctx.obj["project"] = path
    _emit(ctx, proj_core.info(sess.home))


@project.command("info")
@_json_flag
@click.pass_context
def project_info(ctx):
    """Print summary counts for the open project."""
    sess = _load_session(ctx)
    _emit(ctx, proj_core.info(sess.home))


@project.command("save")
@click.option("--as", "as_path", type=click.Path(),
                help="Save to a different path (Save As)")
@click.pass_context
def project_save(ctx, as_path):
    """Save the current project (REPL only)."""
    sess = _load_session(ctx)
    out = sess.save(as_path)
    _emit(ctx, {"saved": out})


@project.command("validate")
@click.option("--strict", is_flag=True,
                help="Exit non-zero on any finding (default: only on errors)")
@click.option("--no-info", is_flag=True,
                help="Suppress purely informational findings")
@_json_flag
@click.pass_context
def project_validate(ctx, strict, no_info):
    """Run every health check (unlinked walls, unknown catalogs,
    degenerate rooms, dangling level refs, doors not on walls,
    lights with no power, …) and emit findings."""
    sess = _load_session(ctx)
    report = validate_core.validate(sess.home, include_info=not no_info)
    if ctx.obj.get("json"):
        out = {
            "ok": report.ok,
            "summary": {
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "infos": len(report.infos),
                "by_code": report.by_code(),
            },
            "findings": [vars(f) for f in report.findings],
        }
        click.echo(json.dumps(out, indent=2, default=str))
    else:
        if not report.findings:
            click.echo("✓ project is clean (no findings)")
        else:
            for f in report.findings:
                tag = {"error":"✗", "warning":"⚠", "info":"●"}[f.severity]
                tgt = ""
                if f.target_name:
                    tgt = f" [{f.target_name}]"
                elif f.target_id:
                    tgt = f" [{f.target_id[:12]}]"
                click.echo(f"{tag} {f.severity:7s} {f.code}{tgt}: {f.message}")
            click.echo()
            click.echo(
                f"summary: {len(report.errors)} error(s), "
                f"{len(report.warnings)} warning(s), "
                f"{len(report.infos)} info(s)"
            )
    if report.errors:
        ctx.exit(1)
    if strict and report.findings:
        ctx.exit(2)


@project.command("bounds")
@click.option("--level", "-l", help="Restrict to one level")
@_json_flag
@click.pass_context
def project_bounds(ctx, level):
    """Overall x/y extent of every wall + room on the project."""
    sess = _load_session(ctx)
    lvl_id = None
    if level is not None:
        lvl = sess.home.find_level(level)
        lvl_id = lvl.id if lvl else level
    xs, ys = [], []
    for w in sess.home.walls:
        if lvl_id and w.level != lvl_id:
            continue
        xs += [w.xStart, w.xEnd]
        ys += [w.yStart, w.yEnd]
    for r in sess.home.rooms:
        if lvl_id and r.level != lvl_id:
            continue
        for p in r.points:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        raise click.ClickException("project has no geometry to bound")
    out = {
        "x_min": min(xs), "x_max": max(xs),
        "y_min": min(ys), "y_max": max(ys),
        "width_cm":  max(xs) - min(xs),
        "depth_cm":  max(ys) - min(ys),
        "width_m":   (max(xs) - min(xs)) / 100,
        "depth_m":   (max(ys) - min(ys)) / 100,
    }
    _emit(ctx, out)


# ─────────────────────────────────────────────────────── level group

@cli.group()
def level():
    """Level: list, add, delete, set."""


@level.command("list")
@_json_flag
@click.pass_context
def level_list(ctx):
    """List all levels."""
    sess = _load_session(ctx)
    _emit(ctx, lvl_core.list_levels(sess.home))


@level.command("add")
@click.argument("name")
@click.option("--elevation", "-e", type=float, default=0, show_default=True)
@click.option("--height", "-h", type=float, default=250, show_default=True)
@click.option("--floor-thickness", type=float, default=12, show_default=True)
@click.pass_context
def level_add(ctx, name, elevation, height, floor_thickness):
    """Add a new level."""
    sess = _load_session(ctx)
    sess.checkpoint()
    lvl = lvl_core.add_level(sess.home, name, elevation=elevation,
                              height=height, floorThickness=floor_thickness)
    _autosave(ctx)
    _emit(ctx, lvl)


@level.command("delete")
@click.argument("ident")
@click.option("--keep-attached", is_flag=True,
                help="Fail if any objects are still attached to this level")
@click.pass_context
def level_delete(ctx, ident, keep_attached):
    """Delete a level by id or name."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        ok = lvl_core.delete_level(sess.home, ident, detach=not keep_attached)
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    if not ok:
        sess.undo()
        raise click.ClickException(f"level not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@level.command("set")
@click.argument("ident")
@click.option("--name", "-n")
@click.option("--elevation", "-e", type=float)
@click.option("--height", "-h", type=float)
@click.option("--floor-thickness", type=float)
@click.option("--elevation-index", type=int,
                help="Reorder this level by elevation index")
@click.option("--visible/--hidden", default=None)
@click.option("--viewable/--unviewable", default=None,
                help="Whether the level is selectable in the GUI")
@_json_flag
@click.pass_context
def level_set(ctx, ident, name, elevation, height, floor_thickness,
                elevation_index, visible, viewable):
    """Edit properties of an existing level in-place."""
    sess = _load_session(ctx)
    sess.checkpoint()
    fields: dict = {}
    if name             is not None: fields["name"] = name
    if elevation        is not None: fields["elevation"] = elevation
    if height           is not None: fields["height"] = height
    if floor_thickness  is not None: fields["floorThickness"] = floor_thickness
    if elevation_index  is not None: fields["elevationIndex"] = elevation_index
    if visible          is not None: fields["visible"] = visible
    if viewable         is not None: fields["viewable"] = viewable
    if not fields:
        sess.undo()
        raise click.UsageError("nothing to set; pass at least one option")
    try:
        lvl = lvl_core.set_level_properties(sess.home, ident, **fields)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"level not found: {ident}")
    except (AttributeError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, lvl)


@level.command("select")
@click.argument("ident", required=False)
@click.option("--clear", is_flag=True, help="Clear the active level selection")
@_json_flag
@click.pass_context
def level_select(ctx, ident, clear):
    """Mark a level as the active selection (or clear it with --clear)."""
    sess = _load_session(ctx)
    sess.checkpoint()
    if clear or ident is None:
        if not clear and ident is None:
            sess.undo()
            raise click.UsageError("pass an IDENT or --clear")
        lvl_core.select_level(sess.home, None)
        _autosave(ctx)
        _emit(ctx, {"selected": None})
        return
    try:
        lvl = lvl_core.select_level(sess.home, ident)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"level not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"selected": lvl.id, "name": lvl.name})


@level.command("duplicate")
@click.argument("src")
@click.option("--name", "new_name", required=True,
                help="Name for the new level")
@click.option("--elevation", type=float,
                help="Z-elevation for the duplicate (default: stack on top of src)")
@click.option("--offset-x", type=float, default=0, show_default=True,
                help="Translate every duplicated object by this much in X")
@click.option("--offset-y", type=float, default=0, show_default=True)
@click.option("--no-walls", is_flag=True)
@click.option("--no-rooms", is_flag=True)
@click.option("--no-furniture", is_flag=True)
@click.option("--no-annotations", is_flag=True,
                help="Skip dimension lines, labels, and polylines")
@_json_flag
@click.pass_context
def level_duplicate(ctx, src, new_name, elevation, offset_x, offset_y,
                      no_walls, no_rooms, no_furniture, no_annotations):
    """Deep-copy a level's geometry to a new level.

    Walls keep their relative neighbour links (wallAtStart/wallAtEnd are
    remapped to the cloned wall ids). Furniture inside groups is NOT
    duplicated.
    """
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        new_lvl = lvl_core.duplicate_level(
            sess.home, src,
            new_name=new_name,
            elevation=elevation,
            offset_x=offset_x,
            offset_y=offset_y,
            include_walls=not no_walls,
            include_rooms=not no_rooms,
            include_furniture=not no_furniture,
            include_annotations=not no_annotations,
        )
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, new_lvl)


# ─────────────────────────────────────────────────────── wall group

@cli.group()
def wall():
    """Wall: list, add, delete, move, rectangle."""


@wall.command("list")
@click.option("--level", "-l", help="Filter by level id")
@_json_flag
@click.pass_context
def wall_list(ctx, level):
    sess = _load_session(ctx)
    _emit(ctx, walls_core.list_walls(sess.home, level=level))


@wall.command("add")
@click.argument("x_start", type=float)
@click.argument("y_start", type=float)
@click.argument("x_end", type=float)
@click.argument("y_end", type=float)
@click.option("--thickness", "-t", type=float, default=7.5, show_default=True)
@click.option("--height", "-h", type=float, default=None,
                help="Wall height in cm (default: home.wallHeight)")
@click.option("--level", "-l", help="Level id to attach to")
@click.option("--left-color", help="Left side color (#RRGGBB or RRGGBB)")
@click.option("--right-color", help="Right side color")
@click.option("--left-texture", "left_texture",
                help="Stock texture catalogId for the left side "
                     "(see `textures list --category Wall`)")
@click.option("--right-texture", "right_texture",
                help="Stock texture catalogId for the right side")
@click.pass_context
def wall_add(ctx, x_start, y_start, x_end, y_end, thickness, height, level,
              left_color, right_color, left_texture, right_texture):
    """Add a single wall segment."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        lt = tex_core.make_texture(left_texture) if left_texture else None
        rt = tex_core.make_texture(right_texture) if right_texture else None
        w = walls_core.add_wall(
            sess.home, x_start, y_start, x_end, y_end,
            thickness=thickness, height=height, level=level,
            leftSideColor=_parse_int_color(left_color),
            rightSideColor=_parse_int_color(right_color),
            leftSideTexture=lt,
            rightSideTexture=rt,
        )
    except (ValueError, KeyError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, w)


@wall.command("delete")
@click.argument("ident")
@click.pass_context
def wall_delete(ctx, ident):
    sess = _load_session(ctx)
    sess.checkpoint()
    if not walls_core.delete_wall(sess.home, ident):
        sess.undo()
        raise click.ClickException(f"wall not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@wall.command("rectangle")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.argument("width", type=float)
@click.argument("depth", type=float)
@click.option("--thickness", "-t", type=float, default=7.5, show_default=True)
@click.option("--height", "-h", type=float, default=None)
@click.option("--level", "-l")
@click.pass_context
def wall_rectangle(ctx, x, y, width, depth, thickness, height, level):
    """Add 4 connected walls forming a closed rectangle."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        walls = walls_core.rectangle(sess.home, x, y, width, depth,
                                       thickness=thickness, height=height,
                                       level=level)
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, walls)


@wall.command("move")
@click.argument("ident")
@click.option("--x-start", type=float)
@click.option("--y-start", type=float)
@click.option("--x-end", type=float)
@click.option("--y-end", type=float)
@_json_flag
@click.pass_context
def wall_move(ctx, ident, x_start, y_start, x_end, y_end):
    """Move one or both endpoints of a wall."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        w = walls_core.move_wall(sess.home, ident,
                                  xStart=x_start, yStart=y_start,
                                  xEnd=x_end, yEnd=y_end)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"wall not found: {ident}")
    _autosave(ctx)
    _emit(ctx, w)


@wall.command("set")
@click.argument("ident")
@click.option("--thickness", "-t", type=float)
@click.option("--height", "-h", type=float)
@click.option("--height-at-end", type=float)
@click.option("--arc-extent", type=float)
@click.option("--left-color")
@click.option("--right-color")
@click.option("--top-color")
@click.option("--pattern")
@click.option("--left-shininess", type=float,
                help="Left-side reflection 0..1")
@click.option("--right-shininess", type=float,
                help="Right-side reflection 0..1")
@click.option("--left-texture", "left_texture",
                help="Apply stock texture to left side (textures list)")
@click.option("--right-texture", "right_texture",
                help="Apply stock texture to right side")
@click.option("--clear-left-texture", is_flag=True,
                help="Remove the left-side texture")
@click.option("--clear-right-texture", is_flag=True,
                help="Remove the right-side texture")
@_json_flag
@click.pass_context
def wall_set(ctx, ident, thickness, height, height_at_end, arc_extent,
              left_color, right_color, top_color, pattern,
              left_shininess, right_shininess,
              left_texture, right_texture,
              clear_left_texture, clear_right_texture):
    """Edit properties of an existing wall in-place."""
    sess = _load_session(ctx)
    sess.checkpoint()
    fields: dict = {}
    if thickness     is not None: fields["thickness"] = thickness
    if height        is not None: fields["height"] = height
    if height_at_end is not None: fields["heightAtEnd"] = height_at_end
    if arc_extent    is not None: fields["arcExtent"] = arc_extent
    if left_color    is not None: fields["leftSideColor"] = _parse_int_color(left_color)
    if right_color   is not None: fields["rightSideColor"] = _parse_int_color(right_color)
    if top_color     is not None: fields["topColor"] = _parse_int_color(top_color)
    if pattern       is not None: fields["pattern"] = pattern
    if left_shininess  is not None: fields["leftSideShininess"] = left_shininess
    if right_shininess is not None: fields["rightSideShininess"] = right_shininess
    try:
        if left_texture  is not None: fields["leftSideTexture"]  = tex_core.make_texture(left_texture)
        if right_texture is not None: fields["rightSideTexture"] = tex_core.make_texture(right_texture)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    if clear_left_texture:  fields["leftSideTexture"] = None
    if clear_right_texture: fields["rightSideTexture"] = None
    if not fields:
        sess.undo()
        raise click.UsageError("nothing to set; pass at least one option")
    try:
        w = walls_core.set_wall_properties(sess.home, ident, **fields)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"wall not found: {ident}")
    except (AttributeError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, w)


@wall.command("baseboard")
@click.argument("ident")
@click.option("--side", type=click.Choice(["left", "right", "both"]),
                default="both", show_default=True)
@click.option("--thickness", type=float, default=1.0, show_default=True,
                help="Baseboard thickness in cm")
@click.option("--height", type=float, default=10.0, show_default=True,
                help="Baseboard height in cm")
@click.option("--color", help="Baseboard color (#RRGGBB)")
@click.option("--texture", "texture_id",
                help="Stock texture catalogId for the baseboard")
@click.option("--clear", is_flag=True,
                help="Remove the baseboard from the chosen side(s) instead")
@_json_flag
@click.pass_context
def wall_baseboard(ctx, ident, side, thickness, height, color, texture_id,
                    clear):
    """Add or clear a skirting-board baseboard on the named wall."""
    sess = _load_session(ctx)
    sess.checkpoint()
    w = sess.home.find_wall(ident)
    if w is None:
        sess.undo()
        raise click.ClickException(f"wall not found: {ident}")
    if clear:
        if side in ("left", "both"):
            w.leftSideBaseboard = None
        if side in ("right", "both"):
            w.rightSideBaseboard = None
    else:
        try:
            tx = tex_core.make_texture(texture_id) if texture_id else None
        except KeyError as e:
            sess.undo()
            raise click.ClickException(str(e))
        bb = Baseboard(
            thickness=thickness, height=height,
            color=_parse_int_color(color), texture=tx,
        )
        if side in ("left", "both"):
            w.leftSideBaseboard = bb
        if side in ("right", "both"):
            # deep-copy so mutating one side later doesn't leak across
            w.rightSideBaseboard = Baseboard(
                thickness=bb.thickness, height=bb.height,
                color=bb.color, texture=bb.texture,
            )
    _autosave(ctx)
    _emit(ctx, w)


@wall.command("split")
@click.argument("ident")
@click.argument("at", metavar="X,Y")
@click.option("--perp-tol", "perp_tol", type=float, default=50.0,
                show_default=True,
                help="Max perpendicular distance from the wall centerline (cm)")
@click.option("--endpoint-tol", "endpoint_tol", type=float, default=1.0,
                show_default=True,
                help="Minimum distance from either existing endpoint (cm)")
@_json_flag
@click.pass_context
def wall_split_cmd(ctx, ident, at, perp_tol, endpoint_tol):
    """Cut a wall at the given X,Y point projected onto its centerline.

    Produces two walls that inherit every property of the original
    (thickness, height, textures, baseboards, colours). Neighbour links
    are remapped so the surrounding wall graph stays internally consistent.
    """
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        ax, ay = _parse_xy(at)
        h1, h2 = walls_core.split_wall(sess.home, ident,
                                          at_x=ax, at_y=ay,
                                          endpoint_tol_cm=endpoint_tol,
                                          perp_tol_cm=perp_tol)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, [h1, h2])


@wall.command("join")
@click.argument("first")
@click.argument("second")
@click.option("--endpoint-tol", "endpoint_tol", type=float, default=1.0,
                show_default=True,
                help="Max gap between the two walls' shared endpoint (cm)")
@click.option("--angle-tol", "angle_tol", type=float, default=2.0,
                show_default=True,
                help="Max angular deviation from collinear (degrees)")
@_json_flag
@click.pass_context
def wall_join_cmd(ctx, first, second, endpoint_tol, angle_tol):
    """Fuse two collinear walls that share an endpoint into one wall.

    Requires both walls to share an endpoint within --endpoint-tol cm,
    lie on the same line within --angle-tol°, sit on the same level, and
    have matching thickness/height. The surviving wall inherits the outer
    neighbour links.
    """
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        survivor = walls_core.join_walls(sess.home, first, second,
                                            endpoint_tol_cm=endpoint_tol,
                                            angle_tol_deg=angle_tol)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, survivor)


@wall.command("length")
@click.argument("ident")
@click.option("--units", type=click.Choice(["cm", "m", "in", "ft"]),
                default="cm", show_default=True)
@_json_flag
@click.pass_context
def wall_length_cmd(ctx, ident, units):
    """Print a wall's length in cm / m / in / ft."""
    sess = _load_session(ctx)
    w = sess.home.find_wall(ident)
    if w is None:
        raise click.ClickException(f"wall not found: {ident}")
    cm = walls_core.length(w)
    converted = {"cm": cm, "m": cm / 100,
                  "in": cm / 2.54, "ft": cm / 30.48}[units]
    _emit(ctx, {"id": w.id, "length": converted, "units": units,
                 "length_cm": cm})


@wall.command("info")
@click.argument("ident")
@_json_flag
@click.pass_context
def wall_info(ctx, ident):
    """Detailed view of a single wall — length, angle, midpoint,
    neighbours, baseboards, textures."""
    sess = _load_session(ctx)
    w = sess.home.find_wall(ident)
    if w is None:
        raise click.ClickException(f"wall not found: {ident}")
    cm = walls_core.length(w)
    angle_rad = math.atan2(w.yEnd - w.yStart, w.xEnd - w.xStart)
    midx = (w.xStart + w.xEnd) / 2
    midy = (w.yStart + w.yEnd) / 2
    _emit(ctx, {
        "id": w.id, "level": w.level,
        "start": {"x": w.xStart, "y": w.yStart},
        "end": {"x": w.xEnd, "y": w.yEnd},
        "midpoint": {"x": midx, "y": midy},
        "length_cm": cm,
        "length_m": cm / 100,
        "angle_rad": angle_rad,
        "angle_deg": math.degrees(angle_rad),
        "thickness": w.thickness,
        "height": w.height,
        "linked": {
            "wall_at_start": w.wallAtStart,
            "wall_at_end": w.wallAtEnd,
            "is_unlinked": not (w.wallAtStart or w.wallAtEnd),
        },
        "left_texture": w.leftSideTexture.catalogId if w.leftSideTexture else None,
        "right_texture": w.rightSideTexture.catalogId if w.rightSideTexture else None,
        "left_color": w.leftSideColor,
        "right_color": w.rightSideColor,
        "left_baseboard": vars(w.leftSideBaseboard) if w.leftSideBaseboard else None,
        "right_baseboard": vars(w.rightSideBaseboard) if w.rightSideBaseboard else None,
    })


# ─────────────────────────────────────────────────────── room group

@cli.group()
def room():
    """Room: list, add, delete."""


@room.command("list")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def room_list(ctx, level):
    sess = _load_session(ctx)
    _emit(ctx, rooms_core.list_rooms(sess.home, level=level))


@room.command("rectangle")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.argument("width", type=float)
@click.argument("depth", type=float)
@click.option("--name", "-n", help="Room name (visible in plan)")
@click.option("--level", "-l")
@click.option("--floor-color", help="Floor color")
@click.option("--ceiling-color", help="Ceiling color")
@click.option("--floor-texture", "floor_texture",
                help="Stock texture catalogId for the floor")
@click.option("--ceiling-texture", "ceiling_texture",
                help="Stock texture catalogId for the ceiling")
@click.option("--area-visible", is_flag=True)
@click.pass_context
def room_rectangle(ctx, x, y, width, depth, name, level, floor_color,
                    ceiling_color, floor_texture, ceiling_texture,
                    area_visible):
    """Add a rectangular room (4 corner points)."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        ft = tex_core.make_texture(floor_texture) if floor_texture else None
        ct = tex_core.make_texture(ceiling_texture) if ceiling_texture else None
        r = rooms_core.add_rectangle_room(
            sess.home, x, y, width, depth, name=name, level=level,
            floorColor=_parse_int_color(floor_color),
            ceilingColor=_parse_int_color(ceiling_color),
            floorTexture=ft, ceilingTexture=ct,
            areaVisible=area_visible,
        )
    except (ValueError, KeyError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, r)


@room.command("add")
@click.option("--points", required=True,
                help="Polygon corners as 'x1,y1 x2,y2 …'")
@click.option("--name", "-n")
@click.option("--level", "-l")
@click.option("--floor-color")
@click.option("--ceiling-color")
@click.option("--floor-texture", "floor_texture",
                help="Stock texture catalogId for the floor")
@click.option("--ceiling-texture", "ceiling_texture",
                help="Stock texture catalogId for the ceiling")
@click.pass_context
def room_add(ctx, points, name, level, floor_color, ceiling_color,
              floor_texture, ceiling_texture):
    """Add a room from arbitrary polygon points."""
    pts: list[tuple[float, float]] = []
    for tok in points.split():
        try:
            xs, ys = tok.split(",")
            pts.append((float(xs), float(ys)))
        except ValueError:
            raise click.UsageError(f"bad point token: {tok!r}")
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        ft = tex_core.make_texture(floor_texture) if floor_texture else None
        ct = tex_core.make_texture(ceiling_texture) if ceiling_texture else None
        r = rooms_core.add_room(sess.home, pts, name=name, level=level,
                                  floorColor=_parse_int_color(floor_color),
                                  ceilingColor=_parse_int_color(ceiling_color),
                                  floorTexture=ft, ceilingTexture=ct)
    except (ValueError, KeyError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, r)


@room.command("set")
@click.argument("ident")
@click.option("--name", "-n")
@click.option("--floor-color", help="Floor color (#RRGGBB)")
@click.option("--ceiling-color", help="Ceiling color (#RRGGBB)")
@click.option("--floor-shininess", type=float, help="Floor reflection 0..1")
@click.option("--ceiling-shininess", type=float, help="Ceiling reflection 0..1")
@click.option("--floor-visible/--floor-hidden", default=None)
@click.option("--ceiling-visible/--ceiling-hidden", default=None)
@click.option("--ceiling-flat/--ceiling-domed", default=None)
@click.option("--area-visible/--area-hidden", default=None)
@click.option("--name-angle", type=float)
@click.option("--name-x-offset", type=float)
@click.option("--name-y-offset", type=float)
@click.option("--area-angle", type=float)
@click.option("--area-x-offset", type=float)
@click.option("--area-y-offset", type=float)
@click.option("--floor-texture", "floor_texture",
                help="Apply stock floor texture (textures list)")
@click.option("--ceiling-texture", "ceiling_texture",
                help="Apply stock ceiling texture")
@click.option("--clear-floor-texture", is_flag=True)
@click.option("--clear-ceiling-texture", is_flag=True)
@_json_flag
@click.pass_context
def room_set(ctx, ident, name, floor_color, ceiling_color,
              floor_shininess, ceiling_shininess,
              floor_visible, ceiling_visible, ceiling_flat, area_visible,
              name_angle, name_x_offset, name_y_offset,
              area_angle, area_x_offset, area_y_offset,
              floor_texture, ceiling_texture,
              clear_floor_texture, clear_ceiling_texture):
    """Edit properties of an existing room in-place."""
    sess = _load_session(ctx)
    sess.checkpoint()
    fields: dict = {}
    if name              is not None: fields["name"] = name
    if floor_color       is not None: fields["floorColor"] = _parse_int_color(floor_color)
    if ceiling_color     is not None: fields["ceilingColor"] = _parse_int_color(ceiling_color)
    if floor_shininess   is not None: fields["floorShininess"] = floor_shininess
    if ceiling_shininess is not None: fields["ceilingShininess"] = ceiling_shininess
    if floor_visible     is not None: fields["floorVisible"] = floor_visible
    if ceiling_visible   is not None: fields["ceilingVisible"] = ceiling_visible
    if ceiling_flat      is not None: fields["ceilingFlat"] = ceiling_flat
    if area_visible      is not None: fields["areaVisible"] = area_visible
    if name_angle        is not None: fields["nameAngle"] = name_angle
    if name_x_offset     is not None: fields["nameXOffset"] = name_x_offset
    if name_y_offset     is not None: fields["nameYOffset"] = name_y_offset
    if area_angle        is not None: fields["areaAngle"] = area_angle
    if area_x_offset     is not None: fields["areaXOffset"] = area_x_offset
    if area_y_offset     is not None: fields["areaYOffset"] = area_y_offset
    try:
        if floor_texture   is not None: fields["floorTexture"]   = tex_core.make_texture(floor_texture)
        if ceiling_texture is not None: fields["ceilingTexture"] = tex_core.make_texture(ceiling_texture)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    if clear_floor_texture:   fields["floorTexture"]   = None
    if clear_ceiling_texture: fields["ceilingTexture"] = None
    if not fields:
        sess.undo()
        raise click.UsageError("nothing to set; pass at least one option")
    try:
        r = rooms_core.set_room_properties(sess.home, ident, **fields)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"room not found: {ident}")
    except (AttributeError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, r)


@room.command("delete")
@click.argument("ident")
@click.pass_context
def room_delete(ctx, ident):
    sess = _load_session(ctx)
    sess.checkpoint()
    if not rooms_core.delete_room(sess.home, ident):
        sess.undo()
        raise click.ClickException(f"room not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@room.command("recompute-points")
@click.argument("ident")
@click.option("--tol", type=float, default=20.0, show_default=True,
                help="Snap tolerance in cm")
@_json_flag
@click.pass_context
def room_recompute(ctx, ident, tol):
    """Snap a room's polygon vertices to nearby wall endpoints."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        r = rooms_core.recompute_room_points(sess.home, ident, tol=tol)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"room not found: {ident}")
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, r)


@room.command("area")
@click.argument("ident")
@click.option("--units", type=click.Choice(["m2", "ft2", "cm2"]),
                default="m2", show_default=True)
@_json_flag
@click.pass_context
def room_area_cmd(ctx, ident, units):
    """Print a room's polygon area in m² / ft² / cm²."""
    sess = _load_session(ctx)
    r = sess.home.find_room(ident)
    if r is None:
        raise click.ClickException(f"room not found: {ident}")
    cm2 = rooms_core.area(r)
    converted = {
        "m2":  cm2 / 10000,
        "cm2": cm2,
        "ft2": cm2 / 929.0304,
    }[units]
    _emit(ctx, {
        "id": r.id, "name": r.name, "level": r.level,
        "area": converted, "units": units, "area_cm2": cm2,
    })


@room.command("info")
@click.argument("ident")
@_json_flag
@click.pass_context
def room_info(ctx, ident):
    """Detailed view of a single room — area, perimeter, bounding box,
    attached walls, furniture count inside, level."""
    sess = _load_session(ctx)
    r = sess.home.find_room(ident)
    if r is None:
        raise click.ClickException(f"room not found: {ident}")
    pts = r.points
    cm2 = rooms_core.area(r)
    perimeter_cm = 0.0
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        perimeter_cm += math.hypot(pts[j].x - pts[i].x, pts[j].y - pts[i].y)
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    # Centroid (for inside-room piece detection)
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    # Furniture inside this room's polygon
    from cli_anything.sweethome3d.core.svg.geometry import point_in_polygon
    poly = [(p.x, p.y) for p in pts]
    inside = sum(1 for f in sess.home.furniture
                  if f.level == r.level and point_in_polygon(f.x, f.y, poly))
    # Bounding walls (within 25 cm of the polygon perimeter)
    walls_on_perim = len(find_core.find_room_walls(sess.home, r))
    _emit(ctx, {
        "id": r.id, "name": r.name, "level": r.level,
        "points": len(pts),
        "area_m2": cm2 / 10000,
        "area_cm2": cm2,
        "perimeter_cm": perimeter_cm,
        "perimeter_m": perimeter_cm / 100,
        "bounds": {"x_min": min(xs), "x_max": max(xs),
                    "y_min": min(ys), "y_max": max(ys),
                    "width_cm": max(xs)-min(xs),
                    "depth_cm": max(ys)-min(ys)},
        "centroid": {"x": cx, "y": cy},
        "bounding_walls": walls_on_perim,
        "furniture_inside": inside,
        "floor_color": r.floorColor,
        "floor_texture": r.floorTexture.catalogId if r.floorTexture else None,
        "ceiling_color": r.ceilingColor,
        "ceiling_texture": r.ceilingTexture.catalogId if r.ceilingTexture else None,
    })


# ─────────────────────────────────────────────────────── furniture group

@cli.group()
def furniture():
    """Furniture: list, add, delete, move."""


@furniture.command("list")
@click.option("--kind", type=click.Choice(furn_core.KINDS))
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def furniture_list(ctx, kind, level):
    sess = _load_session(ctx)
    _emit(ctx, furn_core.list_furniture(sess.home, kind=kind, level=level))


@furniture.command("add")
@click.argument("name")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.option("--width", "-w", type=float, required=True)
@click.option("--depth", "-d", type=float, required=True)
@click.option("--height", "-h", type=float, required=True)
@click.option("--kind", type=click.Choice(furn_core.KINDS),
                default="pieceOfFurniture", show_default=True)
@click.option("--catalog-id")
@click.option("--model", help="Embedded content path (ZIP entry name)")
@click.option("--level", "-l")
@click.option("--elevation", "-e", type=float, default=0, show_default=True)
@click.option("--angle", "-a", type=float, default=0, show_default=True,
                help="Rotation in radians")
@click.option("--color")
@click.option("--power", type=float, help="(light only) brightness 0-1")
@click.pass_context
def furniture_add(ctx, name, x, y, width, depth, height, kind, catalog_id,
                    model, level, elevation, angle, color, power):
    """Add a furniture piece."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        f = furn_core.add_piece(
            sess.home, name, x, y,
            width=width, depth=depth, height=height,
            kind=kind, catalogId=catalog_id, model=model, level=level,
            elevation=elevation, angle=angle,
            color=_parse_int_color(color), power=power,
        )
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, f)


def _maybe_snap(ctx, sess, x, y, level, angle, snap_default):
    """Resolve (x, y, angle) by snapping to nearest wall when requested.

    Returns the (possibly adjusted) (x, y, angle). When --snap is on and no
    wall is found within 200 cm, falls back to the raw input and warns.
    """
    if not snap_default:
        return x, y, angle
    hit = walls_core.nearest_wall(sess.home, x, y, level=level,
                                    max_distance=200.0)
    if hit is None:
        click.echo("warning: --snap on but no wall within 200 cm — using raw "
                    "coordinates and provided --angle", err=True)
        return x, y, angle
    _w, sx, sy, wall_angle, _dist = hit
    return sx, sy, wall_angle


@furniture.command("add-door")
@click.argument("name")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.option("--width", "-w", type=float, default=80, show_default=True)
@click.option("--height", "-h", type=float, default=200, show_default=True)
@click.option("--level", "-l")
@click.option("--angle", "-a", type=float, default=0, show_default=True,
                help="Rotation in radians (ignored when --snap is on)")
@click.option("--catalog-id", default=None,
                help=f"SH3D catalog id (default {furn_core.DEFAULT_DOOR_CATALOG_ID}). "
                      "Browse with `catalog list --kind doorOrWindow`.")
@click.option("--model", default=None,
                help="Embedded content path (ZIP entry name)")
@click.option("--cut-out-shape", default=None,
                help=f"SVG path of the wall cut-out (default {furn_core.DEFAULT_CUT_OUT_SHAPE!r})")
@click.option("--snap/--no-snap", default=True, show_default=True,
                help="Snap to the nearest wall (within 200 cm) and align angle")
@_json_flag
@click.pass_context
def furniture_add_door(ctx, name, x, y, width, height, level, angle,
                        catalog_id, model, cut_out_shape, snap):
    """Add a door (a doorOrWindow with sensible defaults)."""
    sess = _load_session(ctx)
    sess.checkpoint()
    x, y, angle = _maybe_snap(ctx, sess, x, y, level, angle, snap)
    f = furn_core.add_door(sess.home, name, x, y,
                            width=width, height=height,
                            level=level, angle=angle,
                            catalogId=catalog_id, model=model,
                            cutOutShape=cut_out_shape)
    _autosave(ctx)
    _emit(ctx, f)


@furniture.command("add-window")
@click.argument("name")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.option("--width", "-w", type=float, default=100, show_default=True)
@click.option("--height", "-h", type=float, default=120, show_default=True)
@click.option("--elevation", "-e", type=float, default=100, show_default=True)
@click.option("--level", "-l")
@click.option("--angle", "-a", type=float, default=0, show_default=True,
                help="Rotation in radians (ignored when --snap is on)")
@click.option("--catalog-id", default=None,
                help=f"SH3D catalog id (default {furn_core.DEFAULT_WINDOW_CATALOG_ID}). "
                      "Browse with `catalog list --kind doorOrWindow`.")
@click.option("--model", default=None,
                help="Embedded content path (ZIP entry name)")
@click.option("--cut-out-shape", default=None,
                help=f"SVG path of the wall cut-out (default {furn_core.DEFAULT_CUT_OUT_SHAPE!r})")
@click.option("--snap/--no-snap", default=True, show_default=True,
                help="Snap to the nearest wall (within 200 cm) and align angle")
@_json_flag
@click.pass_context
def furniture_add_window(ctx, name, x, y, width, height, elevation, level,
                          angle, catalog_id, model, cut_out_shape, snap):
    """Add a window."""
    sess = _load_session(ctx)
    sess.checkpoint()
    x, y, angle = _maybe_snap(ctx, sess, x, y, level, angle, snap)
    f = furn_core.add_window(sess.home, name, x, y,
                              width=width, height=height,
                              elevation=elevation, level=level, angle=angle,
                              catalogId=catalog_id, model=model,
                              cutOutShape=cut_out_shape)
    _autosave(ctx)
    _emit(ctx, f)


@furniture.command("add-light")
@click.argument("name")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.option("--elevation", "-e", type=float, default=220, show_default=True)
@click.option("--power", type=float, default=0.5, show_default=True)
@click.option("--color", default="#FFFFE0", show_default=True)
@click.option("--catalog-id", default=None,
                help=f"SH3D catalog id (default {furn_core.DEFAULT_LIGHT_CATALOG_ID})")
@click.option("--model", default=None)
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def furniture_add_light(ctx, name, x, y, elevation, power, color, catalog_id,
                          model, level):
    """Add a ceiling/wall light."""
    sess = _load_session(ctx)
    sess.checkpoint()
    f = furn_core.add_light(sess.home, name, x, y,
                             elevation=elevation, power=power,
                             color=_parse_int_color(color) or 0xFFFFFFE0,
                             catalogId=catalog_id, model=model,
                             level=level)
    _autosave(ctx)
    _emit(ctx, f)


@furniture.command("delete")
@click.argument("ident")
@click.pass_context
def furniture_delete(ctx, ident):
    sess = _load_session(ctx)
    sess.checkpoint()
    if not furn_core.delete_piece(sess.home, ident):
        sess.undo()
        raise click.ClickException(f"furniture not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@furniture.command("move")
@click.argument("ident")
@click.option("--x", type=float)
@click.option("--y", type=float)
@click.option("--elevation", "-e", type=float)
@click.option("--angle", "-a", type=float)
@_json_flag
@click.pass_context
def furniture_move(ctx, ident, x, y, elevation, angle):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        f = furn_core.move_piece(sess.home, ident, x=x, y=y,
                                  elevation=elevation, angle=angle)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"furniture not found: {ident}")
    _autosave(ctx)
    _emit(ctx, f)


@furniture.command("set")
@click.argument("ident")
@click.option("--name")
@click.option("--width", "-w", type=float)
@click.option("--depth", "-d", type=float)
@click.option("--height", "-h", type=float)
@click.option("--angle", "-a", type=float)
@click.option("--elevation", "-e", type=float)
@click.option("--color", help="Color (#RRGGBB or RRGGBB)")
@click.option("--catalog-id")
@click.option("--model")
@click.option("--cut-out-shape")
@click.option("--power", type=float, help="(light only) brightness 0-1")
@click.option("--visible/--hidden", default=None)
@click.option("--name-visible/--name-hidden", default=None)
@click.option("--description")
@_json_flag
@click.pass_context
def furniture_set(ctx, ident, name, width, depth, height, angle, elevation,
                    color, catalog_id, model, cut_out_shape, power, visible,
                    name_visible, description):
    """Edit properties of an existing furniture piece in-place."""
    sess = _load_session(ctx)
    sess.checkpoint()
    fields: dict = {}
    if name           is not None: fields["name"] = name
    if width          is not None: fields["width"] = width
    if depth          is not None: fields["depth"] = depth
    if height         is not None: fields["height"] = height
    if angle          is not None: fields["angle"] = angle
    if elevation      is not None: fields["elevation"] = elevation
    if color          is not None: fields["color"] = _parse_int_color(color)
    if catalog_id     is not None: fields["catalogId"] = catalog_id
    if model          is not None: fields["model"] = model
    if cut_out_shape  is not None: fields["cutOutShape"] = cut_out_shape
    if power          is not None: fields["power"] = power
    if visible        is not None: fields["visible"] = visible
    if name_visible   is not None: fields["nameVisible"] = name_visible
    if description    is not None: fields["description"] = description
    if not fields:
        sess.undo()
        raise click.UsageError("nothing to set; pass at least one option")
    try:
        f = furn_core.set_piece_properties(sess.home, ident, **fields)
    except KeyError:
        sess.undo()
        raise click.ClickException(f"furniture not found: {ident}")
    except (AttributeError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, f)


@furniture.command("info")
@click.argument("ident")
@_json_flag
@click.pass_context
def furniture_info(ctx, ident):
    """One-shot detail view of a piece — materials, sashes, light
    sources, properties, position, all in one JSON blob.

    Resolves the piece through `Home.find_furniture`, so grouped pieces
    are reachable by name or id.
    """
    sess = _load_session(ctx)
    f = sess.home.find_furniture(ident)
    if f is None:
        raise click.ClickException(f"furniture not found: {ident}")
    out = vars(f).copy()
    # Convert nested dataclasses for clean JSON output
    out["materials"] = [vars(m) for m in f.materials]
    out["sashes"] = [vars(s) for s in f.sashes]
    out["lightSources"] = [vars(ls) for ls in f.lightSources]
    out["lightSourceMaterials"] = [vars(m) for m in f.lightSourceMaterials]
    out["shelves"] = [vars(sh) for sh in f.shelves]
    out["modelTransformations"] = [vars(t) for t in f.modelTransformations]
    if f.texture:
        out["texture"] = vars(f.texture)
    if f.nameStyle:
        out["nameStyle"] = vars(f.nameStyle)
    _emit(ctx, out)


# ─────────────────────────────────────────────────────── catalog group

@cli.group()
def catalog():
    """Stock SH3D catalog: list, search, info.

    Use this to discover valid `--catalog-id` values for `furniture add`,
    `add-door`, and `add-window`. Selecting a stock id gives SH3D a 3D model
    to render for the piece in the photo view.
    """


@catalog.command("list")
@click.option("--kind", type=click.Choice(furn_core.KINDS),
                help="Filter by kind (doorOrWindow / pieceOfFurniture / light)")
@click.option("--category", "-c",
                help="Filter by category (Doors, Windows, Kitchen, Bedroom, …)")
@_json_flag
@click.pass_context
def catalog_list(ctx, kind, category):
    """List curated stock catalog entries."""
    _emit(ctx, catalog_core.list_catalog(kind=kind, category=category))


@catalog.command("search")
@click.argument("query")
@click.option("--kind", type=click.Choice(furn_core.KINDS))
@_json_flag
@click.pass_context
def catalog_search(ctx, query, kind):
    """Substring-match catalog name or id (case-insensitive)."""
    hits = catalog_core.list_catalog(kind=kind, query=query)
    if not hits:
        raise click.ClickException(f"no catalog entries match {query!r}")
    _emit(ctx, hits)


@catalog.command("info")
@click.argument("catalog_id")
@_json_flag
@click.pass_context
def catalog_info(ctx, catalog_id):
    """Look up a catalog entry by exact catalogId."""
    entry = catalog_core.find_catalog(catalog_id)
    if entry is None:
        raise click.ClickException(f"catalog id not found: {catalog_id}")
    _emit(ctx, entry)


@catalog.command("from-project")
@click.option("--kind", type=click.Choice(furn_core.KINDS),
                help="Filter by kind (doorOrWindow / pieceOfFurniture / light)")
@_json_flag
@click.pass_context
def catalog_from_project(ctx, kind):
    """List every catalogId actually used in the loaded project.

    Surfaces community / non-eTeks catalog ids — the curated `catalog
    list` view is eTeks-only, but real homes lean on contributed
    libraries. Each entry includes the `model` and `icon` ZIP-entry
    paths the project ships with.
    """
    sess = _load_session(ctx)
    entries = catalog_scan_core.from_project(sess.home)
    if kind is not None:
        entries = [e for e in entries if e.kind == kind]
    _emit(ctx, entries)


@catalog.command("scan")
@click.option("--query", "-q",
                help="Substring filter on catalogId or name (case-insensitive)")
@click.option("--kind", type=click.Choice(furn_core.KINDS))
@click.option("--category", "-c", help="Filter by category")
@click.option("--source", help="Filter by source archive filename (substring)")
@click.option("--summary", is_flag=True,
                help="Emit one-row-per-source counts instead of every entry")
@_json_flag
@click.pass_context
def catalog_scan_cmd(ctx, query, kind, category, source, summary):
    """Scan SH3D's Furniture.jar + user .sh3f libraries.

    Reads every catalog properties file on disk and emits one row per
    entry. Use this to discover the real catalogId universe (community
    contributions live in `~/.eteks/sweethome3d/furniture/*.sh3f` and
    aren't visible to `catalog list`).
    """
    entries = catalog_scan_core.scan_all()
    if not entries:
        raise click.ClickException(
            "no catalog archives found. Set SWEETHOME3D_FURNITURE_JAR to "
            "your SH3D Furniture.jar, or install .sh3f libraries under "
            "~/.eteks/sweethome3d/furniture/"
        )
    if kind is not None:
        entries = [e for e in entries if e.kind == kind]
    if category is not None:
        c = category.lower()
        entries = [e for e in entries
                    if e.category and e.category.lower() == c]
    if query is not None:
        q = query.lower()
        entries = [e for e in entries
                    if q in e.catalogId.lower()
                    or (e.name and q in e.name.lower())]
    if source is not None:
        s = source.lower()
        entries = [e for e in entries
                    if e.source and s in e.source.lower()]
    if summary:
        import collections
        by_source = collections.Counter(e.source or "(unknown)" for e in entries)
        rows = [{"source": src, "entries": n}
                 for src, n in by_source.most_common()]
        _emit(ctx, rows)
        return
    _emit(ctx, entries)


# ─────────────────────────────────────────────────────── camera group

@cli.group()
def camera():
    """Camera: top, observer, activate, set."""


@camera.command("get")
@click.option("--kind", type=click.Choice(["topCamera", "observerCamera"]),
                default="topCamera", show_default=True)
@_json_flag
@click.pass_context
def camera_get(ctx, kind):
    sess = _load_session(ctx)
    _emit(ctx, cam_core.get_camera(sess.home, kind=kind))


@camera.command("set")
@click.option("--kind", type=click.Choice(["topCamera", "observerCamera"]),
                default="topCamera", show_default=True)
@click.option("--x", type=float)
@click.option("--y", type=float)
@click.option("--z", type=float)
@click.option("--yaw", type=float)
@click.option("--pitch", type=float)
@click.option("--fov", type=float, help="Field of view (radians)")
@click.option("--lens", type=click.Choice(["PINHOLE", "NORMAL", "FISHEYE", "SPHERICAL"]))
@click.pass_context
def camera_set(ctx, kind, x, y, z, yaw, pitch, fov, lens):
    sess = _load_session(ctx)
    sess.checkpoint()
    cam = cam_core.set_camera(sess.home, kind=kind,
                                x=x, y=y, z=z, yaw=yaw, pitch=pitch,
                                fieldOfView=fov, lens=lens)
    _autosave(ctx)
    _emit(ctx, cam)


@camera.command("activate")
@click.argument("kind", type=click.Choice(["topCamera", "observerCamera"]))
@click.pass_context
def camera_activate(ctx, kind):
    sess = _load_session(ctx)
    sess.checkpoint()
    cam_core.activate_camera(sess.home, kind)
    _autosave(ctx)
    _emit(ctx, {"active": kind})


@camera.command("save")
@click.argument("name")
@click.option("--kind", type=click.Choice(["topCamera", "observerCamera"]),
                default="observerCamera", show_default=True,
                help="Which camera to snapshot")
@_json_flag
@click.pass_context
def camera_save(ctx, name, kind):
    """Save the current camera position as a named stored viewpoint."""
    sess = _load_session(ctx)
    sess.checkpoint()
    if any(c.name == name for c in sess.home.storedCameras):
        sess.undo()
        raise click.ClickException(f"stored camera named {name!r} already exists")
    src = sess.home.observerCamera if kind == "observerCamera" else sess.home.topCamera
    stored = Camera(
        kind=src.kind, name=name,
        x=src.x, y=src.y, z=src.z,
        yaw=src.yaw, pitch=src.pitch, fieldOfView=src.fieldOfView,
        time=src.time, lens=src.lens,
        fixedSize=src.fixedSize, renderer=src.renderer,
    )
    sess.home.storedCameras.append(stored)
    _autosave(ctx)
    _emit(ctx, stored)


@camera.command("list")
@_json_flag
@click.pass_context
def camera_list(ctx):
    """List all stored camera viewpoints."""
    sess = _load_session(ctx)
    _emit(ctx, list(sess.home.storedCameras))


@camera.command("delete")
@click.argument("name")
@click.pass_context
def camera_delete(ctx, name):
    """Delete a stored camera by name."""
    sess = _load_session(ctx)
    sess.checkpoint()
    for c in sess.home.storedCameras:
        if c.name == name:
            sess.home.storedCameras.remove(c)
            _autosave(ctx)
            _emit(ctx, {"deleted": name})
            return
    sess.undo()
    raise click.ClickException(f"stored camera not found: {name}")


@camera.command("go")
@click.argument("name")
@click.option("--target", "target_kind",
                type=click.Choice(["topCamera", "observerCamera"]),
                default="observerCamera", show_default=True,
                help="Which live camera receives the stored position")
@_json_flag
@click.pass_context
def camera_go(ctx, name, target_kind):
    """Load a stored camera's pose into the live top/observer camera."""
    sess = _load_session(ctx)
    sess.checkpoint()
    stored = next((c for c in sess.home.storedCameras if c.name == name), None)
    if stored is None:
        sess.undo()
        raise click.ClickException(f"stored camera not found: {name}")
    cam = sess.home.observerCamera if target_kind == "observerCamera" else sess.home.topCamera
    cam.x = stored.x
    cam.y = stored.y
    cam.z = stored.z
    cam.yaw = stored.yaw
    cam.pitch = stored.pitch
    cam.fieldOfView = stored.fieldOfView
    cam.lens = stored.lens
    if stored.time is not None:
        cam.time = stored.time
    sess.home.camera = target_kind
    _autosave(ctx)
    _emit(ctx, cam)


@camera.command("time")
@click.option("--kind", type=click.Choice(["topCamera", "observerCamera"]),
                default="observerCamera", show_default=True)
@click.option("--year", type=int, default=2024, show_default=True)
@click.option("--month", type=int, default=6, show_default=True,
                help="1=Jan, 12=Dec")
@click.option("--day", type=int, default=21, show_default=True)
@click.option("--hour", type=int, default=12, show_default=True,
                help="0–23")
@click.option("--minute", type=int, default=0, show_default=True)
@click.option("--utc", is_flag=True,
                help="Interpret the date/time as UTC (default: local naive)")
@_json_flag
@click.pass_context
def camera_time(ctx, kind, year, month, day, hour, minute, utc):
    """Set the camera's sun-position time using a natural calendar date.

    SH3D stores `time` as milliseconds-since-epoch (UTC). This command
    hides the encoding so agents can render "afternoon in summer"
    instead of `1719144000000`. Pair with `render photo` to get a
    sunlight angle matching the chosen moment.
    """
    import datetime
    if not 1 <= month <= 12 or not 1 <= day <= 31 or not 0 <= hour <= 23:
        raise click.UsageError(
            "month/day/hour out of range (month 1-12, day 1-31, hour 0-23)"
        )
    try:
        if utc:
            dt = datetime.datetime(year, month, day, hour, minute,
                                     tzinfo=datetime.timezone.utc)
        else:
            dt = datetime.datetime(year, month, day, hour, minute).astimezone()
    except ValueError as e:
        raise click.UsageError(f"invalid date/time: {e}")
    millis = int(dt.timestamp() * 1000)
    sess = _load_session(ctx)
    sess.checkpoint()
    cam = cam_core.set_camera(sess.home, kind=kind, time=millis)
    _autosave(ctx)
    _emit(ctx, {
        "kind": kind,
        "time_ms": millis,
        "iso": dt.isoformat(),
        "summary": dt.strftime("%a %d %b %Y %H:%M %Z").strip(),
    })


# ─────────────────────────────────────────────────────── annotation group

@cli.group()
def dimension():
    """Dimension lines."""


@dimension.command("list")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def dimension_list(ctx, level):
    sess = _load_session(ctx)
    _emit(ctx, ann_core.list_dimensions(sess.home, level=level))


@dimension.command("add")
@click.argument("x_start", type=float)
@click.argument("y_start", type=float)
@click.argument("x_end", type=float)
@click.argument("y_end", type=float)
@click.option("--offset", type=float, default=0)
@click.option("--level", "-l")
@click.option("--color")
@click.pass_context
def dimension_add(ctx, x_start, y_start, x_end, y_end, offset, level, color):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        d = ann_core.add_dimension(sess.home, x_start, y_start, x_end, y_end,
                                     offset=offset, level=level,
                                     color=_parse_int_color(color))
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, d)


@dimension.command("delete")
@click.argument("ident")
@click.pass_context
def dimension_delete(ctx, ident):
    sess = _load_session(ctx)
    sess.checkpoint()
    if not ann_core.delete_dimension(sess.home, ident):
        sess.undo()
        raise click.ClickException(f"dimension not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@dimension.command("set")
@click.argument("ident")
@click.option("--offset", type=float)
@click.option("--color")
@click.option("--end-mark-size", type=float)
@click.option("--elevation-start", type=float)
@click.option("--elevation-end", type=float)
@click.option("--pitch", type=float, help="Rotation around dimension axis (rad)")
@click.option("--visible-in-3d/--invisible-in-3d", default=None)
@_json_flag
@click.pass_context
def dimension_set(ctx, ident, offset, color, end_mark_size,
                    elevation_start, elevation_end, pitch, visible_in_3d):
    """Edit an existing dimension line."""
    sess = _load_session(ctx)
    sess.checkpoint()
    d = None
    for x in sess.home.dimensionLines:
        if x.id == ident:
            d = x
            break
    if d is None:
        sess.undo()
        raise click.ClickException(f"dimension not found: {ident}")
    if offset           is not None: d.offset = offset
    if color            is not None: d.color = _parse_int_color(color)
    if end_mark_size    is not None: d.endMarkSize = end_mark_size
    if elevation_start  is not None: d.elevationStart = elevation_start
    if elevation_end    is not None: d.elevationEnd = elevation_end
    if pitch            is not None: d.pitch = pitch
    if visible_in_3d    is not None: d.visibleIn3D = visible_in_3d
    _autosave(ctx)
    _emit(ctx, d)


@cli.group()
def label():
    """Text labels."""


@label.command("list")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def label_list(ctx, level):
    sess = _load_session(ctx)
    _emit(ctx, ann_core.list_labels(sess.home, level=level))


@label.command("add")
@click.argument("text")
@click.argument("x", type=float)
@click.argument("y", type=float)
@click.option("--level", "-l")
@click.option("--angle", "-a", type=float, default=0)
@click.option("--color")
@click.pass_context
def label_add(ctx, text, x, y, level, angle, color):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        l = ann_core.add_label(sess.home, text, x, y, level=level,
                                 angle=angle, color=_parse_int_color(color))
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, l)


@label.command("delete")
@click.argument("ident")
@click.pass_context
def label_delete(ctx, ident):
    sess = _load_session(ctx)
    sess.checkpoint()
    if not ann_core.delete_label(sess.home, ident):
        sess.undo()
        raise click.ClickException(f"label not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@label.command("set")
@click.argument("ident")
@click.option("--text")
@click.option("--x", type=float)
@click.option("--y", type=float)
@click.option("--angle", "-a", type=float, help="Rotation in radians")
@click.option("--elevation", "-e", type=float)
@click.option("--pitch", type=float)
@click.option("--color")
@click.option("--outline-color")
@_json_flag
@click.pass_context
def label_set(ctx, ident, text, x, y, angle, elevation, pitch, color,
                outline_color):
    """Edit an existing label in-place."""
    sess = _load_session(ctx)
    sess.checkpoint()
    target = None
    for l in sess.home.labels:
        if l.id == ident:
            target = l
            break
    if target is None:
        sess.undo()
        raise click.ClickException(f"label not found: {ident}")
    if text          is not None: target.text = text
    if x             is not None: target.x = x
    if y             is not None: target.y = y
    if angle         is not None: target.angle = angle
    if elevation     is not None: target.elevation = elevation
    if pitch         is not None: target.pitch = pitch
    if color         is not None: target.color = _parse_int_color(color)
    if outline_color is not None: target.outlineColor = _parse_int_color(outline_color)
    _autosave(ctx)
    _emit(ctx, target)


@cli.group()
def compass():
    """Compass (north orientation)."""


@compass.command("get")
@_json_flag
@click.pass_context
def compass_get(ctx):
    sess = _load_session(ctx)
    _emit(ctx, ann_core.get_compass(sess.home))


@compass.command("set")
@click.option("--x", type=float)
@click.option("--y", type=float)
@click.option("--diameter", type=float)
@click.option("--north", "north_direction", type=float,
                help="North direction in radians")
@click.option("--longitude", type=float)
@click.option("--latitude", type=float)
@click.option("--tz", "time_zone")
@click.option("--visible/--hidden", default=None)
@click.pass_context
def compass_set(ctx, x, y, diameter, north_direction, longitude, latitude,
                  time_zone, visible):
    sess = _load_session(ctx)
    sess.checkpoint()
    c = ann_core.set_compass(sess.home,
                               x=x, y=y, diameter=diameter,
                               northDirection=north_direction,
                               longitude=longitude, latitude=latitude,
                               timeZone=time_zone, visible=visible)
    _autosave(ctx)
    _emit(ctx, c)


# ─────────────────────────────────────────────────────── polyline group

@cli.group()
def polyline():
    """Decorative polylines drawn over the plan view."""


@polyline.command("list")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def polyline_list(ctx, level):
    sess = _load_session(ctx)
    _emit(ctx, ann_core.list_polylines(sess.home, level=level))


@polyline.command("add")
@click.option("--points", required=True,
                help="Vertex list as 'x1,y1 x2,y2 …' (min 2 points)")
@click.option("--thickness", "-t", type=float, default=1.0, show_default=True)
@click.option("--color", default=None)
@click.option("--closed/--open", default=False, show_default=True,
                help="Whether to close the path (last point joins first)")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def polyline_add(ctx, points, thickness, color, closed, level):
    """Add a polyline from a list of points."""
    pts: list[tuple[float, float]] = []
    for tok in points.split():
        try:
            xs, ys = tok.split(",")
            pts.append((float(xs), float(ys)))
        except ValueError:
            raise click.UsageError(f"bad point token: {tok!r}")
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        p = ann_core.add_polyline(sess.home, pts,
                                    thickness=thickness,
                                    color=_parse_int_color(color),
                                    closedPath=closed, level=level)
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, p)


@polyline.command("delete")
@click.argument("ident")
@click.pass_context
def polyline_delete(ctx, ident):
    sess = _load_session(ctx)
    sess.checkpoint()
    if not ann_core.delete_polyline(sess.home, ident):
        sess.undo()
        raise click.ClickException(f"polyline not found: {ident}")
    _autosave(ctx)
    _emit(ctx, {"deleted": ident})


@polyline.command("set")
@click.argument("ident")
@click.option("--thickness", "-t", type=float)
@click.option("--color")
@click.option("--closed/--open", "closed_path", default=None)
@click.option("--cap-style", type=click.Choice(["BUTT", "SQUARE", "ROUND"]))
@click.option("--join-style", type=click.Choice(["BEVEL", "MITER", "ROUND",
                                                     "CURVED"]))
@click.option("--dash-style", type=click.Choice(["SOLID", "DOT", "DASH",
                                                     "DASH_DOT", "DASH_DOT_DOT",
                                                     "CUSTOMIZED"]))
@click.option("--dash-pattern", help="Custom dash pattern as space-separated floats")
@click.option("--dash-offset", type=float)
@click.option("--start-arrow",
                type=click.Choice(["NONE", "DELTA", "OPEN", "DISC"]))
@click.option("--end-arrow",
                type=click.Choice(["NONE", "DELTA", "OPEN", "DISC"]))
@click.option("--visible-in-3d/--invisible-in-3d", default=None)
@click.option("--elevation", type=float)
@_json_flag
@click.pass_context
def polyline_set(ctx, ident, thickness, color, closed_path, cap_style,
                  join_style, dash_style, dash_pattern, dash_offset,
                  start_arrow, end_arrow, visible_in_3d, elevation):
    """Edit an existing polyline in-place."""
    sess = _load_session(ctx)
    sess.checkpoint()
    target = None
    for p in sess.home.polylines:
        if p.id == ident:
            target = p
            break
    if target is None:
        sess.undo()
        raise click.ClickException(f"polyline not found: {ident}")
    if thickness     is not None: target.thickness = thickness
    if color         is not None: target.color = _parse_int_color(color)
    if closed_path   is not None: target.closedPath = closed_path
    if cap_style     is not None: target.capStyle = cap_style
    if join_style    is not None: target.joinStyle = join_style
    if dash_style    is not None: target.dashStyle = dash_style
    if dash_pattern  is not None: target.dashPattern = dash_pattern
    if dash_offset   is not None: target.dashOffset = dash_offset
    if start_arrow   is not None: target.startArrowStyle = start_arrow
    if end_arrow     is not None: target.endArrowStyle = end_arrow
    if visible_in_3d is not None: target.visibleIn3D = visible_in_3d
    if elevation     is not None: target.elevation = elevation
    _autosave(ctx)
    _emit(ctx, target)


# ─────────────────────────────────────────────────────── textures group

@cli.group()
def textures():
    """Stock SH3D texture catalog: list, search, info.

    Use this to discover valid texture catalogIds for the `--floor-texture`,
    `--ceiling-texture`, `--left-texture`, `--right-texture`, `--sky-texture`,
    and `--ground-texture` options on `room`, `wall`, and `environment`.
    """


@textures.command("list")
@click.option("--category", "-c",
                type=click.Choice(["Floor", "Wall", "Sky", "floor", "wall", "sky"]),
                help="Filter by texture category")
@_json_flag
@click.pass_context
def textures_list(ctx, category):
    """List curated stock texture entries."""
    _emit(ctx, tex_core.list_textures(category=category))


@textures.command("search")
@click.argument("query")
@click.option("--category", "-c",
                type=click.Choice(["Floor", "Wall", "Sky", "floor", "wall", "sky"]))
@_json_flag
@click.pass_context
def textures_search(ctx, query, category):
    """Substring-match texture name or id (case-insensitive)."""
    hits = tex_core.list_textures(category=category, query=query)
    if not hits:
        raise click.ClickException(f"no textures match {query!r}")
    _emit(ctx, hits)


@textures.command("info")
@click.argument("catalog_id")
@_json_flag
@click.pass_context
def textures_info(ctx, catalog_id):
    """Look up a texture entry by exact catalogId."""
    entry = tex_core.find_texture(catalog_id)
    if entry is None:
        raise click.ClickException(f"unknown texture id: {catalog_id}")
    _emit(ctx, entry)


# ─────────────────────────────────────────────────────── find group

@cli.group()
def find():
    """Locate model objects by spatial / semantic filters.

    Each subcommand is a read-only query that returns the matching objects.
    Designed for agents: combine the JSON output with `wall set`, `room set`,
    `furniture set` to perform targeted edits without manual id-juggling.
    """


def _parse_xy(s: str) -> tuple[float, float]:
    try:
        xs, ys = s.split(",")
        return float(xs), float(ys)
    except (ValueError, AttributeError):
        raise click.UsageError(f"expected X,Y, got {s!r}")


@find.command("rooms")
@click.option("--name", help="Substring match against room name")
@click.option("--level", "-l", help="Level name or id")
@click.option("--contains", help="Keep only rooms whose polygon contains X,Y")
@click.option("--unnamed", is_flag=True,
                help="Only rooms with no name (importer fragments)")
@click.option("--area-min", type=float,
                help="Only rooms with area >= this many m²")
@click.option("--area-max", type=float,
                help="Only rooms with area <= this many m²")
@_json_flag
@click.pass_context
def find_rooms_cmd(ctx, name, level, contains, unnamed, area_min, area_max):
    sess = _load_session(ctx)
    rooms = find_core.find_rooms(sess.home, name=name, level=level)
    if unnamed:
        rooms = [r for r in rooms if not r.name]
    if area_min is not None or area_max is not None:
        rooms = [
            r for r in rooms
            if (area_min is None or rooms_core.area(r) / 10000 >= area_min)
            and (area_max is None or rooms_core.area(r) / 10000 <= area_max)
        ]
    if contains is not None:
        from cli_anything.sweethome3d.core.svg.geometry import point_in_polygon
        cx, cy = _parse_xy(contains)
        rooms = [r for r in rooms
                  if point_in_polygon(cx, cy, [(p.x, p.y) for p in r.points])]
    _emit(ctx, rooms)


@find.command("walls")
@click.option("--near", help="Walls within 25 cm of X,Y (single closest match)")
@click.option("--level", "-l")
@click.option("--horizontal", is_flag=True, help="Only walls aligned to the X axis")
@click.option("--vertical", is_flag=True, help="Only walls aligned to the Y axis")
@click.option("--thickness", type=float,
                help="Only walls matching this thickness (±0.5 cm)")
@click.option("--unlinked", is_flag=True,
                help="Only walls with no wallAtStart and no wallAtEnd "
                     "(surfaces import-corner-fuse failures)")
@click.option("--max-distance", type=float, default=25.0, show_default=True,
                help="Max distance from --near point in cm")
@_json_flag
@click.pass_context
def find_walls_cmd(ctx, near, level, horizontal, vertical, thickness,
                    unlinked, max_distance):
    sess = _load_session(ctx)
    h_flag: Optional[bool] = True if horizontal else None
    v_flag: Optional[bool] = True if vertical else None
    u_flag: Optional[bool] = True if unlinked else None
    if near is not None:
        np = _parse_xy(near)
        w = find_core.find_wall(sess.home, near_point=np, level=level,
                                  horizontal=h_flag, vertical=v_flag,
                                  thickness=thickness,
                                  max_distance_cm=max_distance)
        _emit(ctx, [w] if w is not None else [])
        return
    _emit(ctx, find_core.find_walls(sess.home, level=level,
                                       horizontal=h_flag, vertical=v_flag,
                                       thickness=thickness,
                                       unlinked=u_flag))


@find.command("pieces")
@click.option("--kind", type=click.Choice(furn_core.KINDS))
@click.option("--name")
@click.option("--catalog")
@click.option("--level", "-l")
@click.option("--in-room", "in_room",
                help="Restrict to pieces whose centre falls inside this room")
@click.option("--near", help="Pieces within --max-distance of X,Y")
@click.option("--max-distance", type=float, default=200.0, show_default=True)
@_json_flag
@click.pass_context
def find_pieces_cmd(ctx, kind, name, catalog, level, in_room, near,
                     max_distance):
    sess = _load_session(ctx)
    kwargs: dict = {}
    if kind     is not None: kwargs["kind"] = kind
    if name     is not None: kwargs["name"] = name
    if catalog  is not None: kwargs["catalog"] = catalog
    if level    is not None: kwargs["level"] = level
    if near     is not None: kwargs["near_point"] = _parse_xy(near)
    kwargs["max_distance_cm"] = max_distance
    if in_room is not None:
        room = find_core.find_room(sess.home, name=in_room)
        if room is None:
            raise click.ClickException(f"room not found: {in_room}")
        kwargs["in_room"] = room
    _emit(ctx, find_core.find_pieces(sess.home, **kwargs))


@find.command("doors")
@click.option("--name")
@click.option("--level", "-l")
@click.option("--in-room", "in_room")
@click.option("--near")
@_json_flag
@click.pass_context
def find_doors_cmd(ctx, name, level, in_room, near):
    sess = _load_session(ctx)
    kwargs: dict = {}
    if name  is not None: kwargs["name"] = name
    if level is not None: kwargs["level"] = level
    if near  is not None: kwargs["near_point"] = _parse_xy(near)
    if in_room is not None:
        room = find_core.find_room(sess.home, name=in_room)
        if room is None:
            raise click.ClickException(f"room not found: {in_room}")
        kwargs["in_room"] = room
    _emit(ctx, find_core.find_doors(sess.home, **kwargs))


@find.command("lights")
@click.option("--name")
@click.option("--level", "-l")
@click.option("--in-room", "in_room")
@click.option("--near")
@_json_flag
@click.pass_context
def find_lights_cmd(ctx, name, level, in_room, near):
    sess = _load_session(ctx)
    kwargs: dict = {}
    if name  is not None: kwargs["name"] = name
    if level is not None: kwargs["level"] = level
    if near  is not None: kwargs["near_point"] = _parse_xy(near)
    if in_room is not None:
        room = find_core.find_room(sess.home, name=in_room)
        if room is None:
            raise click.ClickException(f"room not found: {in_room}")
        kwargs["in_room"] = room
    _emit(ctx, find_core.find_lights(sess.home, **kwargs))


# ─────────────────────────────────────────────────────── environment group

@cli.group()
def environment():
    """Environment (sky/ground/lighting/photo)."""


@environment.command("get")
@_json_flag
@click.pass_context
def environment_get(ctx):
    sess = _load_session(ctx)
    _emit(ctx, env_core.get_environment(sess.home))


@environment.command("set")
@click.option("--sky-color")
@click.option("--ground-color")
@click.option("--light-color")
@click.option("--ceiling-light-color")
@click.option("--walls-alpha", type=float)
@click.option("--drawing-mode",
                type=click.Choice(["FILL", "OUTLINE", "FILL_AND_OUTLINE"]))
@click.option("--sky-texture", "sky_texture",
                help="Stock texture catalogId for the sky "
                     "(textures list --category Sky)")
@click.option("--ground-texture", "ground_texture",
                help="Stock texture catalogId for the ground")
@click.option("--clear-sky-texture", is_flag=True)
@click.option("--clear-ground-texture", is_flag=True)
@click.option("--subpart-size-under-light", type=float,
                help="Mesh subdivision under each light (0 = engine default)")
@click.option("--all-levels-visible/--current-level-only", default=None,
                help="Show all level geometry in 3D even when one is selected")
@click.option("--observer-elevation-adjusted/--observer-elevation-fixed",
                default=None,
                help="Whether observer camera elevation tracks the active level")
@click.option("--background-on-ground/--background-off-ground", default=None,
                help="Project the background image onto the 3D ground plane")
@click.pass_context
def environment_set(ctx, sky_color, ground_color, light_color,
                      ceiling_light_color, walls_alpha, drawing_mode,
                      sky_texture, ground_texture,
                      clear_sky_texture, clear_ground_texture,
                      subpart_size_under_light, all_levels_visible,
                      observer_elevation_adjusted, background_on_ground):
    sess = _load_session(ctx)
    sess.checkpoint()
    fields = {}
    if sky_color is not None:    fields["skyColor"] = _parse_int_color(sky_color)
    if ground_color is not None: fields["groundColor"] = _parse_int_color(ground_color)
    if light_color is not None:  fields["lightColor"] = _parse_int_color(light_color)
    if ceiling_light_color is not None:
        fields["ceilingLightColor"] = _parse_int_color(ceiling_light_color)
    if walls_alpha is not None:  fields["wallsAlpha"] = walls_alpha
    if drawing_mode is not None: fields["drawingMode"] = drawing_mode
    try:
        if sky_texture is not None:    fields["skyTexture"]    = tex_core.make_texture(sky_texture)
        if ground_texture is not None: fields["groundTexture"] = tex_core.make_texture(ground_texture)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    if clear_sky_texture:    fields["skyTexture"] = None
    if clear_ground_texture: fields["groundTexture"] = None
    if subpart_size_under_light is not None:
        fields["subpartSizeUnderLight"] = subpart_size_under_light
    if all_levels_visible is not None:
        fields["allLevelsVisible"] = all_levels_visible
    if observer_elevation_adjusted is not None:
        fields["observerCameraElevationAdjusted"] = observer_elevation_adjusted
    if background_on_ground is not None:
        fields["backgroundImageVisibleOnGround3D"] = background_on_ground
    try:
        env = env_core.set_environment(sess.home, **fields)
    except (AttributeError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, env)


@environment.command("photo-size")
@click.argument("width", type=int)
@click.argument("height", type=int)
@click.pass_context
def environment_photo_size(ctx, width, height):
    sess = _load_session(ctx)
    sess.checkpoint()
    env = env_core.set_photo_size(sess.home, width, height)
    _autosave(ctx)
    _emit(ctx, env)


@environment.command("video-size")
@click.argument("width", type=int)
@click.option("--aspect", "aspect_ratio",
                type=click.Choice(["RATIO_4_3", "RATIO_16_9", "RATIO_3_2",
                                   "RATIO_24_10", "RATIO_2_1", "SQUARE_RATIO",
                                   "RATIO_16_10", "VIEW_3D_RATIO"]),
                default="RATIO_4_3", show_default=True)
@click.option("--frame-rate", type=int, default=25, show_default=True)
@click.option("--quality", type=int, default=0, show_default=True,
                help="0=low … 3=best")
@click.option("--speed", type=float, default=240, show_default=True,
                help="Playback speed multiplier (240 = SH3D default)")
@_json_flag
@click.pass_context
def environment_video_size(ctx, width, aspect_ratio, frame_rate, quality, speed):
    """Set the video render dimensions and timing."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        env = env_core.set_video_size(sess.home, width,
                                       aspectRatio=aspect_ratio,
                                       frameRate=frame_rate,
                                       quality=quality, speed=speed)
    except ValueError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, env)


# ─────────────────────────────────────────────────────── export group

@cli.group()
def export():
    """Export the plan to SVG (and other formats)."""


@export.command("svg")
@click.argument("output", type=click.Path())
@click.option("--padding", type=float, default=50, show_default=True)
@click.option("--scale", type=float, default=1.0, show_default=True)
@click.option("--level", "-l")
@click.pass_context
def export_svg_cmd(ctx, output, padding, scale, level):
    """Render the home plan as an SVG file."""
    sess = _load_session(ctx)
    path = export_core.export_svg(sess.home, output,
                                    padding=padding, scale=scale, level=level)
    _emit(ctx, {"exported": path, "format": "svg"})


# ─────────────────────────────────────────────────────── import group

@cli.group("import")
def import_grp():
    """Import external formats into a new .sh3d project."""


@import_grp.command("svg")
@click.option("--spec", "spec_path", required=True, type=click.Path(exists=True),
              help="YAML spec file consumed by svg_to_home_multi()")
@click.option("--output", "-o", "output_path", type=click.Path(),
              default=None, help="Output .sh3d path (overrides spec meta.output)")
@click.option("--name", "-n", default=None,
              help="Home name (overrides spec meta.name)")
@_json_flag
@click.pass_context
def import_svg(ctx, spec_path, output_path, name):
    """Import a YAML spec + SVG floor-plan(s) into a new .sh3d file."""
    try:
        home = svg_to_home_multi(spec=spec_path)
    except Exception as e:
        raise click.ClickException(f"SVG import failed: {e}")

    # Apply --name override
    if name is not None:
        home.name = name

    # Resolve output path: --output > spec meta.output > {meta.name}.sh3d > imported.sh3d
    if output_path is None:
        cfg = load_spec(spec_path)
        meta = cfg.get("meta") or {}
        output_path = meta.get("output") or None
        if output_path is None:
            home_name = home.name or meta.get("name")
            output_path = f"{home_name}.sh3d" if home_name else "imported.sh3d"

    try:
        proj_core.save_home(home, output_path)
    except Exception as e:
        raise click.ClickException(f"save failed: {e}")

    summary = proj_core.info(home)
    result = {
        "created": output_path,
        "name": home.name,
        "levels": summary["levels"],
        "walls": summary["walls"],
        "rooms": summary["rooms"],
        "furniture": summary["furniture"],
        "doors_and_windows": summary["doors_and_windows"],
        "lights": summary["lights"],
    }
    _emit(ctx, result)


# ─────────────────────────────────────────────────────── render group

@cli.group()
def render():
    """Open the project in Sweet Home 3D for photo render."""


@render.command("open")
@click.option("--wait", is_flag=True, help="Wait for SH3D to exit")
@click.pass_context
def render_open(ctx, wait):
    """Launch Sweet Home 3D with the project loaded."""
    sess = _load_session(ctx)
    if not sess.path:
        raise click.ClickException("no project path; save the project first")
    try:
        pid_or_rc = backend.open_in_app(sess.path, wait=wait)
    except backend.Sweethome3DNotInstalled as e:
        raise click.ClickException(str(e))
    _emit(ctx, {"sh3d": sess.path, "wait": wait,
                  ("returncode" if wait else "pid"): pid_or_rc})


@render.command("status")
@click.pass_context
def render_status(ctx):
    """Report whether the Sweet Home 3D binary is reachable."""
    try:
        argv = backend.find_sweethome3d()
        ver = backend.version()
        _emit(ctx, {"installed": True, "argv": argv, "version": ver})
    except backend.Sweethome3DNotInstalled as e:
        _emit(ctx, {"installed": False, "message": str(e)})


@render.command("photo")
@click.argument("output", type=click.Path())
@click.option("--engine",
              type=click.Choice(["gpu_draft", "cpu_photo", "gpu_photo"]),
              default=None,
              help=(
                  "Render engine: gpu_draft (fast OpenGL), cpu_photo (Sunflow GI), "
                  "gpu_photo (Blender Cycles+OptiX). Mutually exclusive with --gpu/--no-gpu."
              ))
@click.option("--gpu/--no-gpu", default=None,
              help="[DEPRECATED] Use --engine instead. "
                   "--gpu maps to gpu_draft, --no-gpu maps to cpu_photo.")
@click.option("--quality", type=click.Choice(["LOW", "MEDIUM", "HIGH"]),
              default="LOW", show_default=True,
              help="Quality level (applies to cpu_photo engine)")
@click.option("--samples", type=int, default=128, show_default=True,
              help="Cycles sample count (applies to gpu_photo engine)")
@click.option("--width", "-w", type=int, default=1400, show_default=True)
@click.option("--height", "-h", type=int, default=900, show_default=True)
@click.option("--from-camera", "from_camera", default=None,
              help="Render from a named stored camera (from `camera save`). "
                   "Loads the stored pose into the active camera before render.")
@click.option("--timeout", "timeout_s", type=int, default=600, show_default=True,
              help="Render timeout in seconds")
@_json_flag
@click.pass_context
def render_photo(ctx, output, engine, gpu, quality, samples, width, height,
                  from_camera, timeout_s):
    """Render a photo-realistic image of the loaded project.

    \b
    Examples:
      render photo out.png --engine gpu_photo --samples 256 -w 1920 -h 1080
      render photo out.png --engine cpu_photo --quality HIGH
      render photo out.png --engine gpu_draft
      render photo out.png --gpu          (deprecated; same as gpu_draft)
      render photo out.png --no-gpu       (deprecated; same as cpu_photo)
    """
    sess = _load_session(ctx)
    if not sess.path:
        raise click.ClickException("no project path; save the project first")

    # --from-camera: load the named stored camera into the active observer
    # camera so the render uses its pose. We save the project after so the
    # downstream Java/Blender path sees the updated camera on disk.
    if from_camera is not None:
        stored = next((c for c in sess.home.storedCameras
                       if c.name == from_camera), None)
        if stored is None:
            raise click.ClickException(
                f"stored camera not found: {from_camera!r}. "
                f"Available: {[c.name for c in sess.home.storedCameras]}"
            )
        # Match the stored camera kind so framing maps cleanly
        target = (sess.home.observerCamera if stored.kind == "observerCamera"
                   else sess.home.topCamera)
        target.x = stored.x; target.y = stored.y; target.z = stored.z
        target.yaw = stored.yaw; target.pitch = stored.pitch
        target.fieldOfView = stored.fieldOfView
        target.lens = stored.lens
        if stored.time is not None:
            target.time = stored.time
        sess.home.camera = stored.kind
        sess.save()

    # Validate mutual exclusivity: --engine and --gpu/--no-gpu are alternatives
    if engine is not None and gpu is not None:
        raise click.UsageError(
            "--engine and --gpu/--no-gpu are mutually exclusive. "
            "Use --engine (preferred) or --gpu/--no-gpu (deprecated)."
        )

    if gpu is not None:
        import warnings
        warnings.warn(
            "--gpu/--no-gpu is deprecated; use --engine gpu_draft or --engine cpu_photo",
            DeprecationWarning,
            stacklevel=1,
        )
        click.echo(
            "warning: --gpu/--no-gpu is deprecated; use --engine instead",
            err=True,
        )

    try:
        from cli_anything.sweethome3d.core.render_runtime import render as _render
    except ImportError as e:
        raise click.ClickException(
            f"render_runtime not available: {e}. "
            "Ensure cli_anything.sweethome3d.core.render_runtime is installed."
        )

    # Build kwargs — let render_runtime handle gpu→engine mapping
    kwargs: dict = dict(
        quality=quality,
        samples=samples,
        width=width,
        height=height,
        timeout_s=timeout_s,
    )
    if engine is not None:
        kwargs["engine"] = engine
    if gpu is not None:
        kwargs["gpu"] = gpu

    try:
        result = _render(sess.path, output, **kwargs)
    except Exception as e:
        raise click.ClickException(f"render failed: {e}")
    _emit(ctx, result)


# ─────────────────────────────────────────────────────── edit group

@cli.group()
def edit():
    """Edit: mutate rooms, walls, lights, and doors in-place."""


@edit.command("floor")
@click.option("--room", "room_name", required=True, help="Room name (substring match)")
@click.option("--level", "level_name", default=None, help="Level name to narrow match")
@click.option("--color", required=True, help="Floor color as #RRGGBB")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Save to a new file instead of in-place")
@_json_flag
@click.pass_context
def edit_floor(ctx, room_name, level_name, color, output):
    """Paint the floor of a named room."""
    from cli_anything.sweethome3d.core import find
    from cli_anything.sweethome3d.core.svg.spec import hex_to_argb
    from cli_anything.sweethome3d.core.project import open_home, save_home

    project_path = ctx.obj.get("project")
    if not project_path:
        raise click.UsageError("--project is required for edit commands")

    home = open_home(project_path)

    candidates = find.find_rooms(home, name=room_name, level=level_name)
    if not candidates:
        raise click.ClickException(f"no room matching {room_name!r}")
    if len(candidates) > 1:
        names = ", ".join(r.name or r.id for r in candidates)
        raise click.ClickException(
            f"multiple rooms match {room_name!r}: {names} — be more specific"
        )
    room = candidates[0]

    before = {"id": room.id, "name": room.name, "floorColor": room.floorColor}
    argb = hex_to_argb(color)
    room.floorColor = argb
    after = {"id": room.id, "name": room.name, "floorColor": room.floorColor}

    dest = output or project_path
    save_home(home, dest)
    _emit(ctx, {
        "changed": f"floor color of room '{room.name}'",
        "id": room.id,
        "before": before,
        "after": after,
        "saved_to": dest,
    })


@edit.command("wall")
@click.option("--near", "near_xy", required=True,
              help="X,Y coordinates near the wall (e.g. 100,200)")
@click.option("--side", type=click.Choice(["north", "south", "east", "west"]),
              default=None, help="Which side of the wall to paint")
@click.option("--color", required=True, help="Color as #RRGGBB")
@click.option("--left-color", "left_color", default=None,
              help="Explicit left-side color override (#RRGGBB)")
@click.option("--right-color", "right_color", default=None,
              help="Explicit right-side color override (#RRGGBB)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Save to a new file instead of in-place")
@_json_flag
@click.pass_context
def edit_wall(ctx, near_xy, side, color, left_color, right_color, output):
    """Paint one side (or both) of the wall nearest to X,Y."""
    from cli_anything.sweethome3d.core import find
    from cli_anything.sweethome3d.core.project import open_home, save_home

    project_path = ctx.obj.get("project")
    if not project_path:
        raise click.UsageError("--project is required for edit commands")

    try:
        x_str, y_str = near_xy.split(",")
        px, py = float(x_str), float(y_str)
    except ValueError:
        raise click.UsageError("--near must be X,Y (e.g. 100,200)")

    home = open_home(project_path)
    w = find.find_wall(home, near_point=(px, py))
    if w is None:
        raise click.ClickException(
            f"no wall found near ({px}, {py}) within 25 cm"
        )

    before = {
        "id": w.id,
        "leftSideColor": w.leftSideColor,
        "rightSideColor": w.rightSideColor,
    }
    argb = _parse_int_color(color)

    if left_color is not None or right_color is not None:
        # Explicit overrides win
        if left_color is not None:
            w.leftSideColor = _parse_int_color(left_color)
        if right_color is not None:
            w.rightSideColor = _parse_int_color(right_color)
        desc = "wall left/right explicit colors"
    elif side is not None:
        # Side-based: map north/south/east/west to left/right using wall angle
        wall_angle = math.atan2(w.yEnd - w.yStart, w.xEnd - w.xStart)
        # SH3D: leftSide is to the left when walking from start→end
        # north face = face with outward normal pointing up (-Y).
        # outward normal for right side: rotate wall_angle by -90°
        right_normal_angle = wall_angle - math.pi / 2
        rn_x = math.cos(right_normal_angle)
        rn_y = math.sin(right_normal_angle)

        # Determine which normal faces the named cardinal direction
        cardinal = {"north": (0, -1), "south": (0, 1),
                    "east": (1, 0), "west": (-1, 0)}
        dx, dy = cardinal[side]
        dot_right = rn_x * dx + rn_y * dy
        if dot_right > 0:
            w.rightSideColor = argb
            desc = f"wall right side ({side})"
        else:
            w.leftSideColor = argb
            desc = f"wall left side ({side})"
    else:
        # Paint both sides
        w.leftSideColor = argb
        w.rightSideColor = argb
        desc = "wall both sides"

    after = {
        "id": w.id,
        "leftSideColor": w.leftSideColor,
        "rightSideColor": w.rightSideColor,
    }
    dest = output or project_path
    save_home(home, dest)
    _emit(ctx, {
        "changed": desc,
        "id": w.id,
        "before": before,
        "after": after,
        "saved_to": dest,
    })


@edit.command("light")
@click.option("--name", "light_name", required=True, help="Light name (substring match)")
@click.option("--in-room", "in_room_name", default=None,
              help="Narrow to lights in this room")
@click.option("--catalog", "catalog_id", required=True,
              help="New SH3D catalog ID for the light")
@click.option("--power", type=float, default=None,
              help="Light power 0..1 (optional)")
@click.option("--color", default=None, help="Light color (#RRGGBB, optional)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Save to a new file instead of in-place")
@_json_flag
@click.pass_context
def edit_light(ctx, light_name, in_room_name, catalog_id, power, color, output):
    """Replace a light's catalog ID and optionally set power/color."""
    from cli_anything.sweethome3d.core import find
    from cli_anything.sweethome3d.core.project import open_home, save_home

    project_path = ctx.obj.get("project")
    if not project_path:
        raise click.UsageError("--project is required for edit commands")

    home = open_home(project_path)

    kwargs: dict = {"name": light_name}
    if in_room_name is not None:
        room = find.find_room(home, name=in_room_name)
        if room is None:
            raise click.ClickException(f"room not found: {in_room_name!r}")
        kwargs["in_room"] = room

    candidates = find.find_lights(home, **kwargs)
    if not candidates:
        raise click.ClickException(f"no light matching {light_name!r}")
    if len(candidates) > 1:
        names = ", ".join(f.name or f.id for f in candidates)
        raise click.ClickException(
            f"multiple lights match {light_name!r}: {names} — be more specific"
        )
    f = candidates[0]

    before = {
        "id": f.id,
        "name": f.name,
        "catalogId": f.catalogId,
        "power": getattr(f, "power", None),
        "color": getattr(f, "color", None),
    }
    f.catalogId = catalog_id
    if power is not None:
        if not (0.0 <= power <= 1.0):
            raise click.UsageError("--power must be between 0 and 1")
        f.power = power
    if color is not None:
        f.color = _parse_int_color(color)

    after = {
        "id": f.id,
        "name": f.name,
        "catalogId": f.catalogId,
        "power": getattr(f, "power", None),
        "color": getattr(f, "color", None),
    }
    dest = output or project_path
    save_home(home, dest)
    _emit(ctx, {
        "changed": f"light '{f.name}' catalogId → {catalog_id}",
        "id": f.id,
        "before": before,
        "after": after,
        "saved_to": dest,
    })


@edit.command("door")
@click.option("--name", "door_name", required=True, help="Door name (substring match)")
@click.option("--near", "near_xy", default=None,
              help="X,Y to narrow match (e.g. 100,200)")
@click.option("--flip", is_flag=True, required=True,
              help="Flip door direction (rotate by π radians)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Save to a new file instead of in-place")
@_json_flag
@click.pass_context
def edit_door(ctx, door_name, near_xy, flip, output):
    """Flip a door's swing direction."""
    from cli_anything.sweethome3d.core import find
    from cli_anything.sweethome3d.core.project import open_home, save_home

    project_path = ctx.obj.get("project")
    if not project_path:
        raise click.UsageError("--project is required for edit commands")

    home = open_home(project_path)

    kwargs: dict = {"name": door_name}
    if near_xy is not None:
        try:
            x_str, y_str = near_xy.split(",")
            kwargs["near_point"] = (float(x_str), float(y_str))
        except ValueError:
            raise click.UsageError("--near must be X,Y (e.g. 100,200)")

    candidates = find.find_doors(home, **kwargs)
    if not candidates:
        raise click.ClickException(f"no door matching {door_name!r}")
    if len(candidates) > 1:
        names = ", ".join(f.name or f.id for f in candidates)
        raise click.ClickException(
            f"multiple doors match {door_name!r}: {names} — use --near to narrow"
        )
    d = candidates[0]

    before = {"id": d.id, "name": d.name, "angle": d.angle}
    d.angle = (d.angle + math.pi) % (2 * math.pi)
    after = {"id": d.id, "name": d.name, "angle": d.angle}

    dest = output or project_path
    save_home(home, dest)
    _emit(ctx, {
        "changed": f"door '{d.name}' flipped",
        "id": d.id,
        "before": before,
        "after": after,
        "saved_to": dest,
    })


# ─────────────────────────────────────────────────────── watch command

@cli.command("watch")
@click.argument("sh3d_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output PNG path (default: same name as .sh3d with .png)")
@click.option("--gpu/--no-gpu", default=True, show_default=True)
@click.option("-w", "--width", "width", type=int, default=1400, show_default=True)
@click.option("-h", "--height", "height", type=int, default=900, show_default=True)
@click.option("--engine", "engine_opts", multiple=True,
              help="Extra engine options (repeatable key=value pairs)")
@click.pass_context
def watch_cmd(ctx, sh3d_path, output, gpu, width, height, engine_opts):
    """Watch a .sh3d file and re-render to PNG on every save.

    Uses the watchdog library when available, otherwise polls mtime every second.
    Press Ctrl-C to stop.
    """
    import time

    if output is None:
        base, _ = os.path.splitext(sh3d_path)
        output = base + ".png"

    # Attempt to import render_runtime eagerly so we fail fast
    try:
        from cli_anything.sweethome3d.core.render_runtime import render as _render
    except ImportError as e:
        raise click.ClickException(
            f"render_runtime not available: {e}. "
            "Ensure cli_anything.sweethome3d.core.render_runtime is installed."
        )

    def _do_render() -> None:
        t0 = time.monotonic()
        try:
            result = _render(
                sh3d_path, output,
                gpu=gpu, width=width, height=height,
            )
            elapsed = result.get("elapsed_s", time.monotonic() - t0)
            engine = result.get("engine", "?")
        except Exception as exc:
            click.echo(f"render error: {exc}", err=True)
            return
        click.echo(f"re-rendered {output} ({elapsed:.1f}s, {engine})")

    # Try watchdog first
    _use_watchdog = False
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        _use_watchdog = True
    except ImportError:
        pass

    click.echo(
        f"watching {sh3d_path} → {output} "
        f"({'watchdog' if _use_watchdog else 'polling'})"
    )

    # Initial render
    _do_render()

    if _use_watchdog:
        watch_dir = os.path.dirname(os.path.abspath(sh3d_path)) or "."
        watch_file = os.path.abspath(sh3d_path)

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if os.path.abspath(event.src_path) == watch_file:
                    _do_render()

        observer = Observer()
        observer.schedule(_Handler(), watch_dir, recursive=False)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
    else:
        last_mtime = os.path.getmtime(sh3d_path)
        try:
            while True:
                time.sleep(1)
                mtime = os.path.getmtime(sh3d_path)
                if mtime != last_mtime:
                    last_mtime = mtime
                    _do_render()
        except KeyboardInterrupt:
            pass

    click.echo("watch stopped.")


# ─────────────────────────────────────────────────────── furniture groups

@cli.group()
def group():
    """Furniture groups: bundle pieces that move/rotate together."""


@group.command("list")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def group_list(ctx, level):
    """List furniture groups, optionally filtered by level."""
    sess = _load_session(ctx)
    _emit(ctx, group_core.list_groups(sess.home, level=level))


@group.command("create")
@click.argument("name")
@click.option("--pieces", "-p", "pieces", required=True,
                help="Comma-separated piece ids or names")
@click.option("--level", "-l", help="Override level (default: first piece's level)")
@_json_flag
@click.pass_context
def group_create(ctx, name, pieces, level):
    """Create a new furniture group from existing pieces."""
    sess = _load_session(ctx)
    sess.checkpoint()
    idents = [p.strip() for p in pieces.split(",") if p.strip()]
    try:
        grp = group_core.create_group(sess.home, name,
                                        piece_idents=idents, level=level)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, grp)


@group.command("info")
@click.argument("ident")
@_json_flag
@click.pass_context
def group_info(ctx, ident):
    sess = _load_session(ctx)
    grp = group_core.find_group(sess.home, ident)
    if grp is None:
        raise click.ClickException(f"group not found: {ident}")
    _emit(ctx, grp)


@group.command("add")
@click.argument("group_ident")
@click.option("--pieces", "-p", "pieces", required=True,
                help="Comma-separated piece ids or names to add")
@_json_flag
@click.pass_context
def group_add(ctx, group_ident, pieces):
    sess = _load_session(ctx)
    sess.checkpoint()
    idents = [p.strip() for p in pieces.split(",") if p.strip()]
    try:
        grp = group_core.add_to_group(sess.home, group_ident, idents)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, grp)


@group.command("remove")
@click.argument("group_ident")
@click.option("--pieces", "-p", "pieces", required=True,
                help="Comma-separated piece ids or names to remove")
@_json_flag
@click.pass_context
def group_remove(ctx, group_ident, pieces):
    sess = _load_session(ctx)
    sess.checkpoint()
    idents = [p.strip() for p in pieces.split(",") if p.strip()]
    try:
        grp = group_core.remove_from_group(sess.home, group_ident, idents)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, grp)


@group.command("ungroup")
@click.argument("ident")
@_json_flag
@click.pass_context
def group_ungroup(ctx, ident):
    """Dissolve a group; members rejoin home.furniture as top-level pieces."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        released = group_core.ungroup(sess.home, ident)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"ungrouped": ident, "released": [p.id for p in released]})


@group.command("delete")
@click.argument("ident")
@click.pass_context
def group_delete(ctx, ident):
    """Delete a group AND its member pieces (use ungroup to keep pieces)."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        deleted = group_core.delete_group(sess.home, ident)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"deleted": ident, "members": len(deleted)})


@group.command("set")
@click.argument("ident")
@click.option("--name")
@click.option("--angle", type=float)
@click.option("--visible/--hidden", "visible", default=None)
@click.option("--movable/--locked", "movable", default=None)
@click.option("--name-visible/--name-hidden", "name_visible", default=None)
@click.option("--price")
@click.option("--description")
@click.option("--creator")
@_json_flag
@click.pass_context
def group_set(ctx, ident, name, angle, visible, movable, name_visible,
                price, description, creator):
    """Update properties on an existing group."""
    sess = _load_session(ctx)
    sess.checkpoint()
    fields = {}
    if name is not None: fields["name"] = name
    if angle is not None: fields["angle"] = angle
    if visible is not None: fields["visible"] = visible
    if movable is not None: fields["movable"] = movable
    if name_visible is not None: fields["nameVisible"] = name_visible
    if price is not None: fields["price"] = price
    if description is not None: fields["description"] = description
    if creator is not None: fields["creator"] = creator
    if not fields:
        sess.undo()
        raise click.UsageError("provide at least one --field option")
    try:
        grp = group_core.set_group_properties(sess.home, ident, **fields)
    except (KeyError, AttributeError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, grp)


# ─────────────────────────────────────────────────────── material group

@cli.group()
def material():
    """Per-piece material overrides: colour, shininess, texture."""


@material.command("list")
@click.argument("piece")
@_json_flag
@click.pass_context
def material_list(ctx, piece):
    sess = _load_session(ctx)
    try:
        _emit(ctx, mat_core.list_materials(sess.home, piece))
    except KeyError as e:
        raise click.ClickException(str(e))


@material.command("set")
@click.argument("piece")
@click.argument("name")
@click.option("--color")
@click.option("--shininess", type=float)
@click.option("--texture", "texture_id", help="Catalog id from `textures list`")
@click.option("--key", help="Material identifier override")
@click.option("--clear-color", is_flag=True)
@click.option("--clear-shininess", is_flag=True)
@click.option("--clear-texture", is_flag=True)
@_json_flag
@click.pass_context
def material_set(ctx, piece, name, color, shininess, texture_id, key,
                   clear_color, clear_shininess, clear_texture):
    """Set or update one material override on a piece."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        mat = mat_core.set_material(
            sess.home, piece, name,
            color=_parse_int_color(color),
            shininess=shininess,
            texture_id=texture_id,
            key=key,
            clear_color=clear_color,
            clear_shininess=clear_shininess,
            clear_texture=clear_texture,
        )
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, mat)


@material.command("clear")
@click.argument("piece")
@click.argument("name")
@click.pass_context
def material_clear(ctx, piece, name):
    """Remove a single material override by name."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        removed = mat_core.clear_material(sess.home, piece, name)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    if not removed:
        sess.undo()
        raise click.ClickException(f"material override not found: {name}")
    _autosave(ctx)
    _emit(ctx, {"cleared": name, "piece": piece})


@material.command("clear-all")
@click.argument("piece")
@click.pass_context
def material_clear_all(ctx, piece):
    """Drop every material override on a piece."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        n = mat_core.clear_all_materials(sess.home, piece)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"piece": piece, "cleared": n})


# ─────────────────────────────────────────────────────── sash group

@cli.group()
def sash():
    """Door / window sashes — pivoting leaf geometry."""


@sash.command("list")
@click.argument("piece")
@_json_flag
@click.pass_context
def sash_list(ctx, piece):
    sess = _load_session(ctx)
    try:
        _emit(ctx, sash_core.list_sashes(sess.home, piece))
    except (KeyError, ValueError) as e:
        raise click.ClickException(str(e))


@sash.command("add")
@click.argument("piece")
@click.option("--x-axis", "x_axis", type=float, required=True,
                help="Pivot X (fraction of piece width)")
@click.option("--y-axis", "y_axis", type=float, required=True,
                help="Pivot Y (fraction of piece depth)")
@click.option("--width", type=float, required=True,
                help="Sash width (fraction of piece width)")
@click.option("--start-angle", "start_angle", type=float, required=True,
                help="Sash start angle (radians)")
@click.option("--end-angle", "end_angle", type=float, required=True,
                help="Sash end angle (radians)")
@_json_flag
@click.pass_context
def sash_add(ctx, piece, x_axis, y_axis, width, start_angle, end_angle):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        s = sash_core.add_sash(sess.home, piece,
                                 xAxis=x_axis, yAxis=y_axis, width=width,
                                 startAngle=start_angle, endAngle=end_angle)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, s)


@sash.command("delete")
@click.argument("piece")
@click.argument("index", type=int)
@click.pass_context
def sash_delete(ctx, piece, index):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        removed = sash_core.delete_sash(sess.home, piece, index)
    except (KeyError, ValueError, IndexError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"deleted": index, "piece": piece, "sash": removed})


@sash.command("clear")
@click.argument("piece")
@click.pass_context
def sash_clear(ctx, piece):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        n = sash_core.clear_sashes(sess.home, piece)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"piece": piece, "cleared": n})


# ─────────────────────────────────────────────────────── emitter group

@cli.group()
def emitter():
    """Per-light point emitters & emissive material groups."""


@emitter.group("source")
def emitter_source():
    """Point emitters inside a light piece."""


@emitter_source.command("list")
@click.argument("piece")
@_json_flag
@click.pass_context
def emitter_source_list(ctx, piece):
    sess = _load_session(ctx)
    try:
        _emit(ctx, light_core.list_sources(sess.home, piece))
    except (KeyError, ValueError) as e:
        raise click.ClickException(str(e))


@emitter_source.command("add")
@click.argument("piece")
@click.option("--x", type=float, required=True, help="0–1 fraction of piece width")
@click.option("--y", type=float, required=True, help="0–1 fraction of piece depth")
@click.option("--z", type=float, required=True, help="0–1 fraction of piece height")
@click.option("--color", required=True, help="AARRGGBB or #RRGGBB")
@click.option("--diameter", type=float, help="Optional emitter diameter (cm)")
@_json_flag
@click.pass_context
def emitter_source_add(ctx, piece, x, y, z, color, diameter):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        src = light_core.add_source(sess.home, piece,
                                       x=x, y=y, z=z,
                                       color=_parse_int_color(color),
                                       diameter=diameter)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, src)


@emitter_source.command("delete")
@click.argument("piece")
@click.argument("index", type=int)
@click.pass_context
def emitter_source_delete(ctx, piece, index):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        removed = light_core.delete_source(sess.home, piece, index)
    except (KeyError, ValueError, IndexError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"deleted": index, "piece": piece, "source": removed})


@emitter_source.command("clear")
@click.argument("piece")
@click.pass_context
def emitter_source_clear(ctx, piece):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        n = light_core.clear_sources(sess.home, piece)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"piece": piece, "cleared": n})


@emitter.group("material")
def emitter_material():
    """Emissive material groups inside a light piece's 3D model."""


@emitter_material.command("list")
@click.argument("piece")
@_json_flag
@click.pass_context
def emitter_material_list(ctx, piece):
    sess = _load_session(ctx)
    try:
        _emit(ctx, light_core.list_materials(sess.home, piece))
    except (KeyError, ValueError) as e:
        raise click.ClickException(str(e))


@emitter_material.command("add")
@click.argument("piece")
@click.argument("name")
@_json_flag
@click.pass_context
def emitter_material_add(ctx, piece, name):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        mat = light_core.add_material(sess.home, piece, name)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, mat)


@emitter_material.command("delete")
@click.argument("piece")
@click.argument("name")
@click.pass_context
def emitter_material_delete(ctx, piece, name):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        removed = light_core.delete_material(sess.home, piece, name)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    if not removed:
        sess.undo()
        raise click.ClickException(f"emissive material not found: {name}")
    _autosave(ctx)
    _emit(ctx, {"deleted": name, "piece": piece})


@emitter_material.command("clear")
@click.argument("piece")
@click.pass_context
def emitter_material_clear(ctx, piece):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        n = light_core.clear_materials(sess.home, piece)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"piece": piece, "cleared": n})


# ─────────────────────────────────────────────────────── shelf group

@cli.group()
def shelf():
    """Shelf-unit shelves — flat planes or 3D box compartments."""


@shelf.command("list")
@click.argument("piece")
@_json_flag
@click.pass_context
def shelf_list(ctx, piece):
    sess = _load_session(ctx)
    try:
        _emit(ctx, shelf_core.list_shelves(sess.home, piece))
    except (KeyError, ValueError) as e:
        raise click.ClickException(str(e))


@shelf.command("add")
@click.argument("piece")
@click.option("--elevation", type=float,
                help="Flat shelf elevation (cm) — mutually exclusive with --bounds")
@click.option("--bounds",
                help="Box shelf bounds: xLo,yLo,zLo,xUp,yUp,zUp (cm)")
@_json_flag
@click.pass_context
def shelf_add(ctx, piece, elevation, bounds):
    if (elevation is None) == (bounds is None):
        raise click.UsageError("supply exactly one of --elevation or --bounds")
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        if elevation is not None:
            sh = shelf_core.add_flat_shelf(sess.home, piece, elevation)
        else:
            parts = [float(p) for p in bounds.split(",")]
            if len(parts) != 6:
                raise click.UsageError(
                    "--bounds requires 6 comma-separated floats: xLo,yLo,zLo,xUp,yUp,zUp"
                )
            xLo, yLo, zLo, xUp, yUp, zUp = parts
            sh = shelf_core.add_box_shelf(sess.home, piece,
                                            xLower=xLo, yLower=yLo, zLower=zLo,
                                            xUpper=xUp, yUpper=yUp, zUpper=zUp)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, sh)


@shelf.command("delete")
@click.argument("piece")
@click.argument("index", type=int)
@click.pass_context
def shelf_delete(ctx, piece, index):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        removed = shelf_core.delete_shelf(sess.home, piece, index)
    except (KeyError, ValueError, IndexError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"deleted": index, "piece": piece, "shelf": removed})


@shelf.command("clear")
@click.argument("piece")
@click.pass_context
def shelf_clear(ctx, piece):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        n = shelf_core.clear_shelves(sess.home, piece)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, {"piece": piece, "cleared": n})


# ─────────────────────────────────────────────────────── background image

@cli.group()
def background():
    """Background plan image — calibrated PNG overlay."""


@background.command("set")
@click.argument("image_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--scale-distance", "scale_distance", type=float, required=True,
                help="Real-world distance (cm) the scale line represents")
@click.option("--x-start", "x_start", type=float, required=True,
                help="Scale line start X (px in source image)")
@click.option("--y-start", "y_start", type=float, required=True,
                help="Scale line start Y (px in source image)")
@click.option("--x-end", "x_end", type=float, required=True,
                help="Scale line end X (px in source image)")
@click.option("--y-end", "y_end", type=float, required=True,
                help="Scale line end Y (px in source image)")
@click.option("--x-origin", "x_origin", type=float, default=0,
                show_default=True, help="Image origin X in plan coordinates")
@click.option("--y-origin", "y_origin", type=float, default=0,
                show_default=True, help="Image origin Y in plan coordinates")
@click.option("--level", "-l",
                help="Attach to a level (default: home root)")
@click.option("--hidden", is_flag=True,
                help="Add invisibly (toggle later with `background show`)")
@_json_flag
@click.pass_context
def background_set(ctx, image_path, scale_distance, x_start, y_start,
                     x_end, y_end, x_origin, y_origin, level, hidden):
    """Attach a calibrated background image to the home or a level."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        bg, _ = bg_core.set_background(
            sess.home,
            image_path=image_path,
            scale_distance_cm=scale_distance,
            scale_x_start=x_start, scale_y_start=y_start,
            scale_x_end=x_end, scale_y_end=y_end,
            x_origin=x_origin, y_origin=y_origin,
            visible=not hidden,
            level=level,
            session_add_content=sess.add_content,
        )
    except (KeyError, ValueError, FileNotFoundError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, bg)


@background.command("clear")
@click.option("--level", "-l")
@click.pass_context
def background_clear(ctx, level):
    """Drop the home or per-level background image."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        ok = bg_core.clear_background(sess.home, level=level)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    if not ok:
        sess.undo()
        target = f"level {level!r}" if level else "home"
        raise click.ClickException(f"no background image on {target}")
    _autosave(ctx)
    _emit(ctx, {"cleared": level or "home"})


@background.command("show")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def background_show(ctx, level):
    """Show (un-hide) the background image."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        bg = bg_core.set_visibility(sess.home, visible=True, level=level)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, bg)


@background.command("hide")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def background_hide(ctx, level):
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        bg = bg_core.set_visibility(sess.home, visible=False, level=level)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, bg)


@background.command("info")
@click.option("--level", "-l")
@_json_flag
@click.pass_context
def background_info(ctx, level):
    sess = _load_session(ctx)
    try:
        bg = bg_core.get_background(sess.home, level=level)
    except KeyError as e:
        raise click.ClickException(str(e))
    if bg is None:
        target = f"level {level!r}" if level else "home"
        raise click.ClickException(f"no background image on {target}")
    _emit(ctx, bg)


# ─────────────────────────────────────────────────────── print settings

@cli.group("print")
def print_grp():
    """Print settings — paper size, margins, orientation, level filter."""


@print_grp.command("get")
@_json_flag
@click.pass_context
def print_get(ctx):
    sess = _load_session(ctx)
    pr = print_core.get_print(sess.home)
    if pr is None:
        raise click.ClickException("no print settings configured")
    _emit(ctx, pr)


@print_grp.command("set")
@click.option("--paper-width", "paper_width", type=float)
@click.option("--paper-height", "paper_height", type=float)
@click.option("--top-margin", "top_margin", type=float)
@click.option("--left-margin", "left_margin", type=float)
@click.option("--bottom-margin", "bottom_margin", type=float)
@click.option("--right-margin", "right_margin", type=float)
@click.option("--orientation",
                type=click.Choice(["PORTRAIT", "LANDSCAPE", "REVERSE_LANDSCAPE"]))
@click.option("--header-format", "header_format")
@click.option("--footer-format", "footer_format")
@click.option("--plan-scale", "plan_scale", type=float,
                help="Plan view scale (e.g. 100 for 1:100)")
@click.option("--furniture-printed/--no-furniture-printed",
                "furniture_printed", default=None)
@click.option("--plan-printed/--no-plan-printed",
                "plan_printed", default=None)
@click.option("--view3d-printed/--no-view3d-printed",
                "view3d_printed", default=None)
@_json_flag
@click.pass_context
def print_set(ctx, paper_width, paper_height, top_margin, left_margin,
               bottom_margin, right_margin, orientation, header_format,
               footer_format, plan_scale, furniture_printed,
               plan_printed, view3d_printed):
    """Create or update print configuration."""
    sess = _load_session(ctx)
    sess.checkpoint()
    fields = {}
    if paper_width is not None: fields["paperWidth"] = paper_width
    if paper_height is not None: fields["paperHeight"] = paper_height
    if top_margin is not None: fields["paperTopMargin"] = top_margin
    if left_margin is not None: fields["paperLeftMargin"] = left_margin
    if bottom_margin is not None: fields["paperBottomMargin"] = bottom_margin
    if right_margin is not None: fields["paperRightMargin"] = right_margin
    if orientation is not None: fields["paperOrientation"] = orientation
    if header_format is not None: fields["headerFormat"] = header_format
    if footer_format is not None: fields["footerFormat"] = footer_format
    if plan_scale is not None: fields["planScale"] = plan_scale
    if furniture_printed is not None: fields["furniturePrinted"] = furniture_printed
    if plan_printed is not None: fields["planPrinted"] = plan_printed
    if view3d_printed is not None: fields["view3DPrinted"] = view3d_printed
    try:
        pr = print_core.set_print(sess.home, **fields)
    except (AttributeError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, pr)


@print_grp.command("clear")
@click.pass_context
def print_clear(ctx):
    """Remove print settings entirely."""
    sess = _load_session(ctx)
    sess.checkpoint()
    if not print_core.clear_print(sess.home):
        sess.undo()
        raise click.ClickException("no print settings to clear")
    _autosave(ctx)
    _emit(ctx, {"cleared": True})


@print_grp.command("add-level")
@click.argument("ident")
@_json_flag
@click.pass_context
def print_add_level(ctx, ident):
    """Include a level in the printout."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        pr = print_core.add_printed_level(sess.home, ident)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, pr)


@print_grp.command("remove-level")
@click.argument("ident")
@_json_flag
@click.pass_context
def print_remove_level(ctx, ident):
    """Exclude a level from the printout."""
    sess = _load_session(ctx)
    sess.checkpoint()
    try:
        pr = print_core.remove_printed_level(sess.home, ident)
    except (KeyError, ValueError) as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, pr)


@print_grp.command("set-levels")
@click.option("--levels", "-L", required=True,
                help="Comma-separated level ids/names; replaces the current list")
@_json_flag
@click.pass_context
def print_set_levels(ctx, levels):
    sess = _load_session(ctx)
    sess.checkpoint()
    idents = [s.strip() for s in levels.split(",") if s.strip()]
    try:
        pr = print_core.set_printed_levels(sess.home, idents)
    except KeyError as e:
        sess.undo()
        raise click.ClickException(str(e))
    _autosave(ctx)
    _emit(ctx, pr)


# ─────────────────────────────────────────────────────── undo/redo

@cli.command("undo")
@click.pass_context
def undo(ctx):
    """Undo the last mutation (REPL only)."""
    sess = _load_session(ctx)
    if sess.undo():
        _emit(ctx, {"undo": True})
    else:
        raise click.ClickException("nothing to undo")


@cli.command("redo")
@click.pass_context
def redo(ctx):
    sess = _load_session(ctx)
    if sess.redo():
        _emit(ctx, {"redo": True})
    else:
        raise click.ClickException("nothing to redo")


@cli.command("status")
@_json_flag
@click.pass_context
def status_cmd(ctx):
    """Show session status (path, modified, undo depth)."""
    sess = _load_session(ctx)
    _emit(ctx, sess.status())


# ─────────────────────────────────────────────────────── REPL

@cli.command("repl", hidden=True)
@click.option("--project-path", "project_path",
                type=click.Path(), default=None,
                help="Project path (auto-load into REPL)")
@click.pass_context
def repl(ctx, project_path):
    """Interactive REPL (default behavior when no subcommand is given)."""
    ctx.obj["in_repl"] = True
    if project_path:
        ctx.obj["project"] = project_path
        if os.path.isfile(project_path):
            try:
                ctx.obj["session"] = Session.open(project_path)
            except Exception as e:
                click.echo(f"warning: could not open {project_path}: {e}")
    skin = ReplSkin("sweethome3d", version=__version__)
    skin.print_banner()
    pt_session = skin.create_prompt_session()
    while True:
        sess: Optional[Session] = ctx.obj.get("session")
        name = (sess.home.name if sess and sess.home else None) or ""
        modified = bool(sess and sess.modified)
        try:
            line = skin.get_input(pt_session,
                                    project_name=name, modified=modified)
        except (EOFError, KeyboardInterrupt):
            break
        line = (line or "").strip()
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        if line in ("help", "?"):
            _print_repl_help(skin)
            continue
        try:
            args = shlex.split(line)
        except ValueError as e:
            skin.error(f"parse error: {e}")
            continue
        try:
            cli.main(args=args, prog_name="cli-anything-sweethome3d",
                      standalone_mode=False, obj=ctx.obj)
        except click.exceptions.UsageError as e:
            skin.error(str(e))
        except click.exceptions.ClickException as e:
            skin.error(e.format_message())
        except SystemExit:
            pass
        except Exception as e:
            skin.error(f"{type(e).__name__}: {e}")
    skin.print_goodbye()


def _print_repl_help(skin: ReplSkin) -> None:
    commands = {
        "project": "new / open / info / save",
        "level": "list / add / delete / set / select",
        "wall": "list / add / rectangle / move / set / baseboard / delete",
        "room": "list / rectangle / add / set / recompute-points / delete",
        "furniture": "list / add / add-door / add-window / add-light / move / set / delete",
        "group": "list / create / info / add / remove / ungroup / delete / set",
        "material": "list / set / clear / clear-all",
        "sash": "list / add / delete / clear",
        "emitter": "source list/add/delete/clear • material list/add/delete/clear",
        "shelf": "list / add / delete / clear",
        "catalog": "list / search / info",
        "textures": "list / search / info",
        "camera": "get / set / activate / save / list / delete / go",
        "dimension": "list / add / set / delete",
        "label": "list / add / set / delete",
        "polyline": "list / add / set / delete",
        "compass": "get / set",
        "environment": "get / set / photo-size / video-size",
        "background": "set / clear / show / hide / info",
        "print": "get / set / clear / add-level / remove-level / set-levels",
        "find": "rooms / walls / pieces / doors / lights",
        "export": "svg",
        "import": "svg",
        "render": "open / status / photo",
        "edit": "floor / wall / light / door",
        "watch": "(standalone — watches a .sh3d and re-renders on save)",
        "undo / redo / status / quit": "",
    }
    skin.help(commands)


def main():
    cli(prog_name="cli-anything-sweethome3d")


if __name__ == "__main__":
    main()
