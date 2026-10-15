"""Coordinate and gridding primitives, independent of PDAL."""

import hashlib

import numpy as np
from pyproj import CRS, Transformer
from rasterio.transform import from_origin
from scipy.spatial import cKDTree


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def coordinate_plan(source, target, vertical_reference):
    if source is None:
        raise ValueError(
            "Missing embedded CRS: obtain authoritative metadata; do not guess."
        )
    source = CRS.from_user_input(source)
    target = CRS.from_user_input(target)
    parts = source.sub_crs_list if source.is_compound else [source]
    horizontal = next((c for c in parts if c.is_projected or c.is_geographic), None)
    vertical = next((c for c in parts if c.is_vertical), None)
    if horizontal is None or vertical is None:
        raise ValueError("Explicit horizontal and vertical CRS required.")
    if (
        not target.is_projected
        or len(target.axis_info) != 2
        or any(abs(a.unit_conversion_factor - 1) > 1e-12 for a in target.axis_info)
    ):
        raise ValueError("Target must be a two-dimensional projected CRS in metres.")
    if vertical_reference.casefold() not in vertical.name.casefold():
        raise ValueError("Vertical reference disagrees with embedded CRS.")
    if horizontal.geodetic_crs.datum != target.geodetic_crs.datum:
        raise ValueError(
            "Horizontal datum change requires a separately reviewed transformation."
        )
    factor = vertical.axis_info[0].unit_conversion_factor
    return (
        Transformer.from_crs(horizontal, target, always_xy=True, allow_ballpark=False),
        factor,
        {
            "source_horizontal_wkt": horizontal.to_wkt(),
            "source_vertical_wkt": vertical.to_wkt(),
            "target_horizontal_wkt": target.to_wkt(),
            "vertical_to_metre": factor,
            "vertical_operation": "Unit conversion only; vertical reference retained. No geoid/datum transformation.",
            "target_vertical_reference": vertical_reference,
            "horizontal_operation": f"{horizontal.name} -> {target.name} (always_xy=True)",
        },
    )


def grid(bounds, resolution):
    xmin, ymin, xmax, ymax = map(float, bounds)
    if (
        not np.isfinite([xmin, ymin, xmax, ymax, resolution]).all()
        or resolution <= 0
        or xmax <= xmin
        or ymax <= ymin
    ):
        raise ValueError("Invalid grid extent or resolution.")
    w = (xmax - xmin) / resolution
    h = (ymax - ymin) / resolution
    if not np.isclose(w, round(w)) or not np.isclose(h, round(h)):
        raise ValueError("Bounds must align with resolution.")
    w, h = round(w), round(h)
    if w * h > 4000000:
        raise ValueError("Grid exceeds memory limit.")
    xx, yy = np.meshgrid(
        xmin + (np.arange(w) + 0.5) * resolution,
        ymax - (np.arange(h) + 0.5) * resolution,
    )
    return (
        np.column_stack([xx.ravel(), yy.ravel()]),
        (h, w),
        from_origin(xmin, ymax, resolution, resolution),
    )


def cell_index(x, y, bounds, resolution, shape):
    xmin, ymin, xmax, ymax = bounds
    x = np.asarray(x)
    y = np.asarray(y)
    keep = (x >= xmin) & (x < xmax) & (y >= ymin) & (y < ymax)
    rows = np.minimum(np.floor((ymax - y[keep]) / resolution).astype(int), shape[0] - 1)
    cols = np.floor((x[keep] - xmin) / resolution).astype(int)
    return keep, rows * shape[1] + cols


def terrain(xy, z, queries, radius=10, k=8):
    """IDW squared of up to k ground neighbors strictly within support radius."""
    xy = np.asarray(xy)
    z = np.asarray(z)
    queries = np.asarray(queries)
    if len(xy) < 3:
        raise ValueError("At least three ground points required.")
    if radius <= 0 or k < 1:
        raise ValueError("Invalid interpolation support.")
    d, i = cKDTree(xy).query(
        queries, k=min(k, len(xy)), distance_upper_bound=radius, workers=1
    )
    if d.ndim == 1:
        d = d[:, None]
        i = i[:, None]
    valid = np.isfinite(d)
    safe = np.minimum(i, len(z) - 1)
    weights = np.where(valid, 1 / np.maximum(d, 1e-9) ** 2, 0)
    denom = weights.sum(axis=1)
    values = np.divide(
        (weights * z[safe]).sum(axis=1),
        denom,
        out=np.full(len(queries), np.nan),
        where=denom > 0,
    )
    return values, valid.sum(axis=1), np.where(valid, d, np.inf).min(axis=1)


def maximum(values, indices, size):
    out = np.full(size, -np.inf)
    np.maximum.at(out, indices, values)
    out[~np.isfinite(out)] = np.nan
    return out


def quantile(values, indices, size, q=0.95):
    out = np.full(size, np.nan)
    order = np.argsort(indices)
    ids = indices[order]
    vals = values[order]
    for group in np.split(np.arange(len(ids)), np.flatnonzero(np.diff(ids)) + 1):
        if len(group):
            out[ids[group[0]]] = np.quantile(vals[group], q)
    return out


def finite_summary(a):
    a = np.asarray(a)
    v = a[np.isfinite(a)]
    return {
        "valid_cells": len(v),
        "total_cells": int(a.size),
        "valid_fraction": float(len(v) / a.size),
        **{
            k: float(f(v)) if len(v) else None
            for k, f in [
                ("min", np.min),
                ("median", np.median),
                ("p95", lambda x: np.quantile(x, 0.95)),
                ("max", np.max),
            ]
        },
    }
