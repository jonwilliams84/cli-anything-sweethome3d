"""Camera control — top-down and first-person observer."""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import Camera, Home


def get_camera(home: Home, *, kind: str = "topCamera") -> Camera:
    if kind == "topCamera":
        return home.topCamera
    if kind == "observerCamera":
        return home.observerCamera
    raise ValueError(f"kind must be 'topCamera' or 'observerCamera', got {kind!r}")


def set_camera(home: Home, *, kind: str = "topCamera",
                x: Optional[float] = None, y: Optional[float] = None,
                z: Optional[float] = None,
                yaw: Optional[float] = None, pitch: Optional[float] = None,
                fieldOfView: Optional[float] = None,
                lens: Optional[str] = None,
                time: Optional[int] = None) -> Camera:
    cam = get_camera(home, kind=kind)
    if x is not None: cam.x = x
    if y is not None: cam.y = y
    if z is not None: cam.z = z
    if yaw is not None: cam.yaw = yaw
    if pitch is not None: cam.pitch = pitch
    if fieldOfView is not None: cam.fieldOfView = fieldOfView
    if lens is not None:
        if lens not in ("PINHOLE", "NORMAL", "FISHEYE", "SPHERICAL"):
            raise ValueError(f"invalid lens: {lens!r}")
        cam.lens = lens
    if time is not None: cam.time = time
    return cam


def activate_camera(home: Home, kind: str) -> None:
    """Set which camera is active (`camera=` attribute on <home>)."""
    if kind not in ("topCamera", "observerCamera"):
        raise ValueError(f"kind must be 'topCamera' or 'observerCamera', got {kind!r}")
    home.camera = kind
