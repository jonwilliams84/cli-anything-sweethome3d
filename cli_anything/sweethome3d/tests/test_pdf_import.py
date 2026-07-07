"""Tests for pdf_import — build a tiny synthetic vector floorplan PDF in-memory
(a filled-poché box with one internal wall), convert it, and assert the walls
come out in the right places. No external fixture needed; skips if PyMuPDF absent.
"""
import math
import pytest

fitz = pytest.importorskip("fitz")  # PyMuPDF

from cli_anything.sweethome3d.core import pdf_import as pi
from cli_anything.sweethome3d.core.project import save_home, open_home


def _fill_rect(page, rect, colour=(0, 0, 0)):
    """Draw one filled rect as its OWN path (real plans store one fill per path)."""
    sh = page.new_shape()
    sh.draw_rect(rect)
    sh.finish(fill=colour, color=colour)
    sh.commit()


def _synthetic_plan(tmp_path):
    """A 300x200pt room outline (black poché, 8pt thick) + one internal wall.
    Each wall is a separate filled path, as in a real vector plan."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    t = 8
    for r in [
        fitz.Rect(50, 50, 350, 50 + t),      # top
        fitz.Rect(50, 250 - t, 350, 250),    # bottom
        fitz.Rect(50, 50, 50 + t, 250),      # left
        fitz.Rect(350 - t, 50, 350, 250),    # right
        fitz.Rect(200 - t / 2, 50, 200 + t / 2, 250),  # internal vertical divider
    ]:
        _fill_rect(page, r)
    p = tmp_path / "plan.pdf"
    doc.save(str(p))
    return str(p)


def test_pdf_to_home_extracts_walls(tmp_path):
    pdf = _synthetic_plan(tmp_path)
    home = pi.pdf_to_home(pdf, scale_cm_per_pt=1.0, min_wall_cm=10, weld_cm=6)
    # 4 envelope walls + 1 divider = 5 (poché runs merge to centrelines)
    assert 4 <= len(home.walls) <= 6
    # extent should be ~300 x 200 cm (the outline), origin near 0
    xmax = max(max(w.xStart, w.xEnd) for w in home.walls)
    ymax = max(max(w.yStart, w.yEnd) for w in home.walls)
    assert 290 <= xmax <= 310
    assert 190 <= ymax <= 210


def test_pdf_home_roundtrips_to_sh3d(tmp_path):
    pdf = _synthetic_plan(tmp_path)
    home = pi.pdf_to_home(pdf, scale_cm_per_pt=1.0, min_wall_cm=10, weld_cm=6)
    out = tmp_path / "plan.sh3d"
    save_home(home, str(out))
    reopened = open_home(str(out))
    assert len(reopened.walls) == len(home.walls)


def test_internal_divider_present(tmp_path):
    pdf = _synthetic_plan(tmp_path)
    home = pi.pdf_to_home(pdf, scale_cm_per_pt=1.0, min_wall_cm=10, weld_cm=6)
    # a vertical wall near x=200 spanning most of the height
    # origin shifts the left wall to x=0, so the divider (paper x=200) lands at ~150
    verticals = [w for w in home.walls if abs(w.xStart - w.xEnd) < 2]
    assert any(abs((w.xStart + w.xEnd) / 2 - 150) < 15 and abs(w.yEnd - w.yStart) > 150
               for w in verticals)


def test_grey_new_walls_classified(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    sh = page.new_shape()
    sh.draw_rect(fitz.Rect(20, 20, 180, 28))   # black existing
    sh.finish(fill=(0, 0, 0), color=(0, 0, 0))
    sh2 = page.new_shape()
    sh2.draw_rect(fitz.Rect(20, 120, 180, 128))  # grey new
    sh2.finish(fill=(0.5, 0.5, 0.5), color=(0.5, 0.5, 0.5))
    sh.commit(); sh2.commit()
    p = tmp_path / "mixed.pdf"; doc.save(str(p))
    home = pi.pdf_to_home(str(p), scale_cm_per_pt=1.0, min_wall_cm=10, weld_cm=6)
    assert len(home.walls) == 2
