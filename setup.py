from setuptools import setup, find_namespace_packages

with open("cli_anything/sweethome3d/README.md") as f:
    long_description = f.read()

setup(
    name="cli-anything-sweethome3d",
    version="1.0.0",
    description="CLI harness for Sweet Home 3D 7.x — interior design from the command line",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    extras_require={
        "watch": ["watchdog>=3.0.0"],
        "pdf": ["PyMuPDF>=1.23.0"],  # vector floorplan PDF -> sh3d (core.pdf_import)
    },
    entry_points={
        "console_scripts": [
            "cli-anything-sweethome3d=cli_anything.sweethome3d.sweethome3d_cli:main",
        ],
    },
    package_data={
        "cli_anything.sweethome3d": ["skills/*.md", "README.md", "examples/*.yaml", "examples/*.md"],
    },
    include_package_data=True,
    python_requires=">=3.10",
)
