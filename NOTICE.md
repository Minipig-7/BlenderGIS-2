# NOTICE

## Attribution

BlenderGIS was originally created and written by **domlysz**
(<https://github.com/domlysz>).

- Original project: <https://github.com/domlysz/BlenderGIS>
- Copyright (C) domlysz and BlenderGIS contributors

This repository is a **derivative work** of the original BlenderGIS project. It
is an unofficial clone, developed independently and separately from the
original. The original author does not sponsor, maintain, or endorse this fork.

## License

The original BlenderGIS project is distributed under the **GNU General Public
License, version 3** (`bl_info['license'] = 'GPL'` in `__init__.py`).

As a derivative work, this repository is distributed under the same license, as
required by GPL-3.0 sections 4 and 5. The complete license text is in
[LICENSE](LICENSE).

No copyright notices have been removed from the source files. Original copyright
and attribution are preserved throughout the codebase.

## What was changed relative to upstream

This fork started from upstream version **2.2.14**. Changes made in this
repository include:

- Fixes and improvements to existing functionality
- Performance optimization
- New functionality
- Code refactoring for readability and modern Python standards

The goals of this fork are described in [README.md](README.md). Individual
changes are recorded under `docs/changes/`.

## Third-party components

This repository vendors or depends on third-party libraries. Those components
remain under their own licenses, as stated in their respective source trees and
project pages:

### Vendored in-tree

| Path | Origin | License |
|---|---|---|
| `core/lib/shapefile.py` | pyshp 2.1.0 by jlawhead (geospatialpython.com) | MIT |
| `core/lib/shapefile123.py` | pyshp 1.2.3 by jlawhead, Python 3 fork | MIT |
| `core/lib/imageio/` | imageio contributors, vendored subset | BSD |
| `core/lib/imghdr.py` | CPython stdlib module | PSF |

### Runtime dependencies

Not vendored — resolved from `requirements.txt` / the user's Blender Python.

| Component | License |
|---|---|
| GDAL / `osgeo` (optional) | MIT |
| PROJ / pyproj (optional) | MIT |
| NumPy | BSD-3-Clause |
| Pillow | MIT-CMU |
| PyQt6 | GPL-3.0 or commercial |
| tifffile / tiffdata / tifftools | BSD / MIT |

Optional dependencies (GDAL, PyProj, ImageIO FreeImage) are detected at import in
`core/checkdeps.py` and the code degrades gracefully when they are absent.

Verify the license of any component in use before redistributing this add-on.