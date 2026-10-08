"""Estimate the RAM needed to import a raster as DEM.

Used to prevent Blender from crashing on out of memory when importing
very large raster files. This module must not import bpy.
"""

import math
import logging

log = logging.getLogger(__name__)

# Blender loads non byte images as a float RGBA buffer (4 channels * 4 bytes)
BLENDER_IMAGE_BYTES_PER_PIXEL = 16

# Conservative estimate for a mesh built from a regular grid with the numpy fast path:
# numpy transient arrays (coords + faces) + final Blender mesh (vertices, corners, polygons)
MESH_BYTES_PER_GRID_VERTEX = 150


def estimateImportBytes(w: int, h: int, depth: int,
                        step: int=1,
                        mesh: bool=False,
                        texture: bool=False,
                        cast: bool=False,
                        fill: bool=False) -> dict:
    """Estimate RAM needed to import a raster.

    w, h : raster size in pixels
    depth : bit depth (8, 16, 32 ...)
    step : pixel step used to build the mesh (does not affect reading and texture)
    mesh : a mesh will be built from pixels (DEM_RAW mode or mesh subdivision)
    texture : the raster will also be loaded as a Blender image texture (displacement mode)
    cast : data will be cast to float32
    fill : nodata values will be filled (needs an extra float copy)
    """
    step = max(1, int(step))
    px = w * h
    meshPx = math.ceil(w / step) * math.ceil(h / step)

    parts = {}
    parts['read'] = px * depth / 8  # raw numpy array
    if cast:
        parts['cast'] = px * 4  # float32 copy
    if fill:
        parts['fill'] = px * 4  # extra float32 copy made by the inpainting function
    if texture:
        parts['texture'] = px * BLENDER_IMAGE_BYTES_PER_PIXEL
    if mesh:
        parts['mesh'] = meshPx * MESH_BYTES_PER_GRID_VERTEX
    parts['total'] = sum(parts.values())
    return parts


def maxFittingStep(w: int, h: int, depth: int,
                   budget: int,
                   texture: bool=False,
                   cast: bool=False,
                   fill: bool=False,
                   maxStep: int=256) -> int:
    """Return the smallest pixel step that makes the import fit into the given budget.
    Return -1 if even reading the raster (without any mesh) does not fit.
    Note : step only reduces the mesh size, reading and texture buffers
    always scale with the full raster size.
    """
    fixed = estimateImportBytes(w, h, depth, step=1, mesh=False,
                                texture=texture, cast=cast, fill=fill)['total']
    if fixed > budget:
        return -1
    meshFull = MESH_BYTES_PER_GRID_VERTEX * math.ceil(w) * math.ceil(h)
    if fixed + meshFull <= budget:
        return 1
    # mesh size scales as 1/step^2, solve directly then validate
    step = math.ceil(math.sqrt(meshFull / max(budget - fixed, 1)))
    step = max(2, min(step, maxStep))
    while step <= maxStep:
        est = estimateImportBytes(w, h, depth, step=step, mesh=True,
                                  texture=texture, cast=cast, fill=fill)
        if est['total'] <= budget:
            return step
        step += 1
    return -1


def getBudget(percent: int, freeRAM: int | None=None) -> int:
    """Compute the RAM budget in bytes from a percentage of available RAM.
    If freeRAM cannot be detected (0) return 0 (guard disabled)."""
    if freeRAM is None:
        from ..utils.meminfo import getFreeRAM
        freeRAM = getFreeRAM()
    if freeRAM <= 0:
        return 0
    return int(freeRAM * percent / 100)
