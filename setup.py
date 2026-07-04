#!/usr/bin/env python3
"""
Setup script for cli-anything-sweethome3d

Install (dev mode):
    pip install -e .

Build:
    python -m build

Publish:
    twine upload dist/*
"""

from pathlib import Path
from setuptools import setup, find_namespace_packages

ROOT = Path(__file__).parent
README = ROOT / "cli_anything/sweethome3d/skills/01-furniture-catalog.md"

long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="cli-anything-sweethome3d",
    version="1.0.0",
    description=(
        "Designer API for SweetHome3D — build .sh3d floor-plans from Python or JSON specs. "
        "LLM-ergonomic: introspection, validation, and spec round-trip built in."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",

    author="cli-anything contributors",
    author_email="",
    url="https://github.com/HKUDS/CLI-Anything",

    project_urls={
        "Source":  "https://github.com/HKUDS/CLI-Anything",
        "Tracker": "https://github.com/HKUDS/CLI-Anything/issues",
    },

    license="MIT",

    packages=find_namespace_packages(include=("cli_anything.*",)),

    python_requires=">=3.10",

    install_requires=[
        # No hard runtime dependencies — pure stdlib for the core.
        # Optional: Pillow for higher-quality PNG renders.
        # Optional: cairosvg for SVG→PNG fallback.
    ],

    extras_require={
        "render": [
            "Pillow>=9",
        ],
        "dev": [
            "pytest>=7",
            "pytest-cov>=4",
        ],
    },

    entry_points={
        "console_scripts": [
            "cli-anything-sweethome3d=cli_anything.sweethome3d.core.__main__:main",
        ],
    },

    package_data={
        "cli_anything.sweethome3d": ["skills/*.md"],
    },
    include_package_data=True,
    zip_safe=False,

    keywords=[
        "cli",
        "sweethome3d",
        "floor-plan",
        "architecture",
        "home-design",
        "llm",
        "automation",
    ],

    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Graphics :: 3D Modeling",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",

        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
