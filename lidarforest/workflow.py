"""End-to-end processing. Input remains unchanged; output promotion is staged."""

import csv
import datetime
import importlib.metadata
import json
import platform
import shutil
import tempfile
from pathlib import Path

import laspy
import numpy as np
import rasterio
import yaml

from .core import (
    cell_index,
    coordinate_plan,
    finite_summary,
    grid,
    maximum,
    quantile,
    sha256,
    terrain,
)


def ingest(path, cfg):
    chunks = []
    total = 0
    removed = 0
    spatial = 0
    retained = 0
    with laspy.open(path) as reader:
        header = reader.header.copy()
        transform, zfactor, plan = coordinate_plan(
            header.parse_crs(), cfg["target_crs"], cfg["vertical_reference"]
        )
        xmin, ymin, xmax, ymax = cfg["bounds"]
        b = cfg["buffer_m"]
        for pts in reader.chunk_iterator(500000):
            total += len(pts)
            x, y = transform.transform(np.asarray(pts.x), np.asarray(pts.y))
            z = np.asarray(pts.z) * zfactor
            within = (x >= xmin - b) & (x < xmax + b) & (y >= ymin - b) & (y < ymax + b)
            spatial += int(within.sum())
            valid = (
                np.isfinite(x)
                & np.isfinite(y)
                & np.isfinite(z)
                & ~np.asarray(pts.withheld, dtype=bool)
                & ~np.isin(pts.classification, [7, 18])
            )
            removed += int((within & ~valid).sum())
            keep = within & valid
            if keep.any():
                a = np.empty(
                    int(keep.sum()),
                    dtype=[
                        ("X", "f8"),
                        ("Y", "f8"),
                        ("Z", "f8"),
                        ("Classification", "u1"),
                        ("ReturnNumber", "u1"),
                        ("NumberOfReturns", "u1"),
                    ],
                )
                for name, v in [
                    ("X", x),
                    ("Y", y),
                    ("Z", z),
                    ("Classification", np.asarray(pts.classification)),
                    ("ReturnNumber", np.asarray(pts.return_number)),
                    ("NumberOfReturns", np.asarray(pts.number_of_returns)),
                ]:
                    a[name] = v[keep]
                chunks.append(a)
                retained += len(a)
                if retained > cfg["max_points"]:
                    raise ValueError(
                        "Buffered sample exceeds max_points; choose smaller bounds."
                    )
    if not chunks:
        raise ValueError("No usable points in study window.")
    return np.concatenate(chunks), {
        "source_points": total,
        "buffered_points_before_filter": spatial,
        "excluded_flagged_or_nonfinite": removed,
        "retained_buffered_points": retained,
        "las_version": str(header.version),
        "point_format": header.point_format.id,
        "source_scales": header.scales.tolist(),
        "source_offsets": header.offsets.tolist(),
        "source_header_bounds": [header.mins.tolist(), header.maxs.tolist()],
        "coordinates": plan,
    }


def classify(a, settings, out):
    import pdal

    stages = [
        {"type": "filters.assign", "value": "Classification = 0"},
        dict(type="filters.smrf", **settings),
    ]
    pipeline = pdal.Pipeline(json.dumps(stages), arrays=[a.copy()])
    pipeline.execute()
    classified = pipeline.arrays[0]
    if len(classified) != len(a) or any(
        not np.array_equal(classified[n], a[n]) for n in ["X", "Y", "Z"]
    ):
        raise ValueError("PDAL changed point order/count; comparison unsafe.")
    (out / "pdal_pipeline.json").write_text(
        json.dumps({"pipeline": stages}, indent=2), encoding="utf-8", newline="\n"
    )
    metadata = pipeline.metadata
    (out / "pdal_metadata.json").write_text(
        json.dumps(
            json.loads(metadata) if isinstance(metadata, str) else metadata, indent=2
        ),
        encoding="utf-8",
        newline="\n",
    )
    return classified


def raster(path, array, shape, transform, crs, unit):
    values = np.asarray(array, dtype="float32").reshape(shape)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999,
        compress="deflate",
        tiled=True,
    ) as dst:
        dst.write(np.where(np.isfinite(values), values, -9999), 1)
        dst.set_band_unit(1, unit)
        dst.update_tags(
            vertical_reference="NAVD88; retained from source",
            method="See run.json; no independent field accuracy validation",
        )


def run(
    config="config/example.yml", output="data/processed", report_assets="report/assets"
):
    cfg = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
    path = Path(cfg["input"])
    out = Path(output)
    if cfg["vertical_reference"] != "NAVD88":
        raise ValueError("Only NAVD88 vertical output metadata is supported.")
    if out.exists():
        raise ValueError(
            f"{out} exists. Choose a new --output directory; existing products are never overwritten."
        )
    if cfg["buffer_m"] < max(cfg["ground_radius_m"], cfg["smrf"]["window"]):
        raise ValueError("Buffer must cover ground support and SMRF window.")
    centres, shape, affine = grid(cfg["bounds"], cfg["resolution_m"])
    a, meta = ingest(path, cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="lidar-stage-", dir=out.parent))
    try:
        c = classify(a, cfg["smrf"], stage)
        keep, idx = cell_index(
            a["X"], a["Y"], cfg["bounds"], cfg["resolution_m"], shape
        )
        n = int(np.prod(shape))
        ground = a["Classification"] == 2
        newground = c["Classification"] == 2
        if ground.sum() < 3 or newground.sum() < 3:
            raise ValueError("Insufficient ground support in a comparison branch.")
        xy = np.column_stack([a["X"], a["Y"]])
        z = a["Z"]
        dtm, support, dist = terrain(
            xy[ground],
            z[ground],
            centres,
            cfg["ground_radius_m"],
            cfg["ground_neighbors"],
        )
        alternate, _, _ = terrain(
            xy[newground],
            z[newground],
            centres,
            cfg["ground_radius_m"],
            cfg["ground_neighbors"],
        )
        local_ground, _, _ = terrain(
            xy[ground],
            z[ground],
            xy[keep],
            cfg["ground_radius_m"],
            cfg["ground_neighbors"],
        )
        hag = z[keep] - local_ground
        cls = a["Classification"][keep]
        veg = np.isin(cls, cfg["vegetation_classes"]) & np.isfinite(hag)
        density = np.bincount(idx, minlength=n) / cfg["resolution_m"] ** 2
        dsm = maximum(z[keep], idx, n)
        chm = dsm - dtm
        p95 = quantile(hag[veg], idx[veg], n)
        denominator = np.bincount(idx[np.isfinite(hag)], minlength=n)
        numerator = np.bincount(
            idx[veg & (hag > cfg["vegetation_threshold_m"])], minlength=n
        )
        fraction = np.divide(
            numerator, denominator, out=np.full(n, np.nan), where=denominator > 0
        )
        rasters = {
            "dtm_provider": (dtm, "m"),
            "dtm_smrf": (alternate, "m"),
            "dtm_difference_smrf_minus_provider": (alternate - dtm, "m"),
            "dsm": (dsm, "m"),
            "surface_height": (chm, "m"),
            "vegetation_p95": (p95, "m"),
            "return_density": (density, "returns/m2"),
            "vegetation_return_fraction_above_threshold": (fraction, "1"),
            "vegetation_return_count": (np.bincount(idx[veg], minlength=n), "returns"),
            "ground_support_count": (support, "neighbors"),
            "nearest_ground_distance": (np.where(np.isfinite(dist), dist, np.nan), "m"),
        }
        for name, (values, unit) in rasters.items():
            raster(
                stage / (name + ".tif"), values, shape, affine, cfg["target_crs"], unit
            )
        header = laspy.LasHeader(point_format=7, version="1.4")
        header.scales = [0.001, 0.001, 0.001]
        header.offsets = [cfg["bounds"][0], cfg["bounds"][1], 0]
        from pyproj import CRS

        # Explicit horizontal+vertical output metadata; NAVD88 is retained.
        header.add_crs(CRS.from_user_input(cfg["target_crs"] + "+5703"))
        las = laspy.LasData(header)
        las.x = a["X"][keep]
        las.y = a["Y"][keep]
        las.z = z[keep]
        las.classification = cls
        las.return_number = a["ReturnNumber"][keep]
        las.number_of_returns = a["NumberOfReturns"][keep]
        las.add_extra_dim(
            laspy.ExtraBytesParams(name="SMRFClassification", type=np.uint8)
        )
        las["SMRFClassification"] = c["Classification"][keep]
        las.add_extra_dim(
            laspy.ExtraBytesParams(name="HeightAboveGround", type=np.float32)
        )
        las["HeightAboveGround"] = hag.astype("float32")
        las.write(stage / "normalized_subset.laz")
        edges = np.array([-np.inf, 0, 2, 5, 10, 20, 40, np.inf])
        counts, _ = np.histogram(hag[veg], edges)
        with (stage / "vertical_profile.csv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["lower_m", "upper_m", "vegetation_returns"])
            w.writerows(zip(edges[:-1], edges[1:], counts.tolist()))
        agreement = {
            "both_ground": int((ground[keep] & newground[keep]).sum()),
            "provider_only_ground": int((ground[keep] & ~newground[keep]).sum()),
            "smrf_only_ground": int((~ground[keep] & newground[keep]).sum()),
            "neither_ground": int((~ground[keep] & ~newground[keep]).sum()),
        }
        summary = {
            "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "input_sha256": sha256(path),
            "config": cfg,
            "ingestion": meta,
            "aoi_points": int(keep.sum()),
            "classification_counts": {
                str(k): int(v) for k, v in zip(*np.unique(cls, return_counts=True))
            },
            "ground_label_comparison": agreement,
            "products": {k: finite_summary(v[0]) for k, v in rasters.items()},
            "quality": {
                "negative_surface_height_cells": int((chm < 0).sum()),
                "negative_vegetation_hag_returns": int((hag[veg] < 0).sum()),
                "vegetation_hag_over_60m_returns": int((hag[veg] > 60).sum()),
                "unsupported_point_hag": int((~np.isfinite(hag)).sum()),
                "empty_return_cells": int((density == 0).sum()),
                "independent_accuracy_validation": False,
            },
            "software": {
                "python": platform.python_version(),
                **{
                    k: importlib.metadata.version(k)
                    for k in ["numpy", "scipy", "laspy", "rasterio", "pyproj", "pdal"]
                },
            },
            "limitations": [
                "Mixed urban/woodland demonstration, not a representative forest inventory.",
                "Ground-label disagreement is not classification accuracy.",
                "Return fractions are not canopy cover, biomass, fuel load or fire risk.",
                "No vertical datum change; unit conversion only.",
                "IDW can bridge small gaps within radius; no independent terrain reference.",
                "Unknown point-data reuse terms; source/subset excluded from Git.",
            ],
        }
        from .figures import draw

        draw(stage, rasters, shape, cfg, a[keep], hag, c["Classification"][keep])
        summary["product_sha256"] = {
            f.name: sha256(f) for f in stage.iterdir() if f.is_file()
        }
        (stage / "run.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False),
            encoding="utf-8",
            newline="\n",
        )
        validate(stage)
        stage.rename(out)
        if report_assets:
            assets = Path(report_assets)
            assets.mkdir(parents=True, exist_ok=True)
            for f in out.glob("*.png"):
                shutil.copy2(f, assets / f.name)
            shutil.copy2(out / "run.json", assets / "run.json")
            from .report import update

            update(assets)
        return summary
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def validate(output):
    out = Path(output)
    m = json.loads((out / "run.json").read_text(encoding="utf-8"))
    for name, expected in m["product_sha256"].items():
        f = (out / name).resolve()
        if f.parent != out.resolve() or sha256(f) != expected:
            raise ValueError("Missing or altered product: " + name)
    cfg = m["config"]
    _, shape, affine = grid(cfg["bounds"], cfg["resolution_m"])
    for f in out.glob("*.tif"):
        with rasterio.open(f) as r:
            from pyproj import CRS

            if (
                r.crs != CRS.from_user_input(cfg["target_crs"])
                or r.nodata != -9999
                or r.shape != shape
                or r.transform != affine
            ):
                raise ValueError("Unexpected raster CRS, nodata or grid.")
    with laspy.open(out / "normalized_subset.laz") as r:
        if (
            r.header.point_count != m["aoi_points"]
            or not r.header.parse_crs().is_compound
        ):
            raise ValueError("Subset count/vertical CRS lost.")
    if sum(m["ground_label_comparison"].values()) != m["aoi_points"]:
        raise ValueError("Comparison does not reconcile.")
    return m
