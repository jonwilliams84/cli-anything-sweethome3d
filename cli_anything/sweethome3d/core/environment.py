"""Environment settings — sky, ground, lighting, photo/video defaults."""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import Environment, Home


def get_environment(home: Home) -> Environment:
    return home.environment


def set_environment(home: Home, **fields) -> Environment:
    """Set any combination of environment attributes."""
    env = home.environment
    for k, v in fields.items():
        if not hasattr(env, k):
            raise AttributeError(f"unknown environment field: {k!r}")
        setattr(env, k, v)
    return env


def set_photo_size(home: Home, width: int, height: int) -> Environment:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    home.environment.photoWidth = width
    home.environment.photoHeight = height
    return home.environment


def set_video_size(home: Home, width: int, *,
                     aspectRatio: str = "RATIO_4_3",
                     frameRate: int = 25,
                     quality: int = 0,
                     speed: float = 240) -> Environment:
    if width <= 0:
        raise ValueError("width must be positive")
    home.environment.videoWidth = width
    home.environment.videoAspectRatio = aspectRatio
    home.environment.videoFrameRate = frameRate
    home.environment.videoQuality = quality
    home.environment.videoSpeed = speed
    return home.environment
