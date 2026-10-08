"""Fast numpy based mesh building from DEM raster data.

Replaces the per pixel python loop of the legacy exportAsMesh function.
Verts and faces are computed with numpy and injected into the mesh with
foreach_set, which is orders of magnitude faster and much lighter in RAM
than python lists of tuples.
"""

import math
import logging

import numpy as np
import bpy

log = logging.getLogger(__name__)

# number of points per batch when reprojecting vertex coordinates
REPROJ_BATCH_SIZE = 1000000

# max step value accepted by the auto step computation
MAX_AUTO_STEP = 256


def reprojXYArrays(reproj, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reproject flat numpy arrays of coordinates in batches.
    reproj.pts() only accepts a list of (x, y) tuples, so we feed it
    batches of points to keep memory bounded."""
    n = xs.size
    outXs = np.empty(n, dtype=np.float64)
    outYs = np.empty(n, dtype=np.float64)
    for i in range(0, n, REPROJ_BATCH_SIZE):
        sl = slice(i, min(i + REPROJ_BATCH_SIZE, n))
        pts = list(zip(xs[sl].tolist(), ys[sl].tolist()))
        rpts = reproj.pts(pts)
        rarr = np.asarray(rpts, dtype=np.float64)
        outXs[sl] = rarr[:, 0]
        outYs[sl] = rarr[:, 1]
    return outXs, outYs


def buildDEMmesh(name: str,
                 georef,
                 dx: float, dy: float,
                 zz: np.ndarray | None=None,
                 step: int=1,
                 noData=None,
                 buildFaces: bool=True,
                 reproj=None,
                 scale: float=1,
                 zScale: float=1):
    """Build a mesh from a georef grid (fast numpy path).

    georef : GeoRef of the raster (already adjusted against the subset if needed)
    dx, dy : scene origin shift (crs units)
    zz : 2D numpy array of pixel values at full raster resolution, or None for a flat grid
    step : pixel step
    noData : nodata value, vertices at nodata are filtered out
    buildFaces : build quad faces connecting the grid points
    reproj : optional Reproj object
    scale : scene scale, 1 blender unit = scale crs units
    zScale : elevation conversion factor (meters to blender units)
    """
    scale = scale if scale else 1
    step = max(1, int(step))

    x0, y0 = georef.origin.x, georef.origin.y  # pixel center
    pxSizeX, pxSizeY = georef.pxSize.x, georef.pxSize.y
    w, h = georef.rSize.x, georef.rSize.y

    # adjust grid size and pixel size against step
    w2, h2 = math.ceil(w / step), math.ceil(h / step)
    pxSizeX, pxSizeY = pxSizeX * step, pxSizeY * step

    x = x0 + pxSizeX * np.arange(w2, dtype=np.float64)
    y = y0 + pxSizeY * np.arange(h2, dtype=np.float64)
    xx, yy = np.meshgrid(x, y)  # shape (h2, w2), same ordering as legacy (px + py * w)

    if reproj is not None:
        xs, ys = reprojXYArrays(reproj, xx.ravel(), yy.ravel())
        xx = xs.reshape(h2, w2)
        yy = ys.reshape(h2, w2)

    # shift and convert to blender units (1 bu = scale crs units)
    xx = (xx - dx) / scale
    yy = (yy - dy) / scale

    if zz is None:  # flat grid
        zzData = np.zeros((h2, w2), dtype=np.float64)
        zzMask = None
    else:
        if zz.ndim == 3:
            raise ValueError('Cannot build a DEM mesh from a multiband raster')
        zz2 = zz[::step, ::step]
        if zz2.shape != (h2, w2):
            # raster size and array shape can slightly differ, adjust the grid
            h2, w2 = zz2.shape
            xx, yy = xx[:h2, :w2], yy[:h2, :w2]
        if np.ma.isMaskedArray(zz2):
            zzMask = np.ma.getmaskarray(zz2)
            zzData = zz2.data
        else:
            zzMask = None
            zzData = zz2

    # validity mask
    valid = np.ones(zzData.shape, dtype=bool)
    if noData is not None:
        if isinstance(noData, float) and math.isnan(noData):
            valid = ~np.isnan(zzData)
        else:
            valid = zzData != noData
    if zzMask is not None:
        valid &= ~zzMask
    if np.issubdtype(zzData.dtype, np.floating):
        valid &= ~np.isnan(zzData)

    validFlat = valid.ravel()
    nValid = int(validFlat.sum())

    # compacted vertex index map (-1 for discarded vertices)
    newIdx = np.where(validFlat, np.cumsum(validFlat) - 1, -1)

    co = np.empty((nValid, 3), dtype=np.float64)
    co[:, 0] = xx.ravel()[validFlat]
    co[:, 1] = yy.ravel()[validFlat]
    co[:, 2] = zzData.ravel()[validFlat] * zScale

    # build faces (same winding as the legacy function)
    nf = 0
    fIdx = None
    if buildFaces and h2 > 1 and w2 > 1:
        v = np.arange(h2 * w2, dtype=np.int64).reshape(h2, w2)
        faceValid = valid[:-1, 1:] & valid[:-1, :-1] & valid[1:, :-1] & valid[1:, 1:]
        f = np.stack([v[:-1, 1:][faceValid],  # v4 top right
                      v[:-1, :-1][faceValid],  # v3 top left
                      v[1:, :-1][faceValid],  # v2 bottom left
                      v[1:, 1:][faceValid]],  # v1 bottom right
                     axis=1)
        fIdx = newIdx[f]
        nf = fIdx.shape[0]

    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(nValid)
    mesh.vertices.foreach_set("co", co.ravel())

    if nf > 0:
        corners = fIdx.astype(np.int32).ravel()
        try:
            mesh.loops.add(corners.size)
            mesh.loops.foreach_set("vertex_index", corners)
            mesh.polygons.add(nf)
            starts = np.arange(0, corners.size, 4, dtype=np.int32)
            mesh.polygons.foreach_set("loop_start", starts)
            try:
                # loop_total was removed in Blender 4.1
                mesh.polygons.foreach_set("loop_total", np.full(nf, 4, dtype=np.int32))
            except (AttributeError, RuntimeError):
                pass
            mesh.update(calc_edges=True)
        except (AttributeError, RuntimeError):
            # fallback to the universal python path (slow but always available)
            log.warning('Fast mesh injection failed, fallback to from_pydata')
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(co.tolist(), [], fIdx.tolist())
            mesh.update()

    mesh.validate(verbose=False)
    mesh.update()
    return mesh
