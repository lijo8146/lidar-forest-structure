"""Refresh report numbers; editable prose lives in docs/report-templates."""

import json
from pathlib import Path


def update(assets):
    assets = Path(assets)
    root = Path(__file__).resolve().parents[1]
    m = json.loads((assets/"run.json").read_text(encoding="utf-8"))
    a = m["ground_label_comparison"]
    p = m["products"]
    d = p["dtm_difference_smrf_minus_provider"]
    disagreement = a["provider_only_ground"] + a["smrf_only_ground"]
    values = {
        "aoi_points": f"{m['aoi_points']:,}",
        "disagreement": f"{disagreement:,}",
        "disagreement_percent": f"{100 * disagreement / m['aoi_points']:.2f}",
        "diff_median": f"{d['median']:.3f}",
        "diff_min": f"{d['min']:.3f}",
        "diff_max": f"{d['max']:.3f}",
        "terrain_valid": f"{p['dtm_provider']['valid_cells']:,}",
        "total_cells": f"{p['dtm_provider']['total_cells']:,}",
        "veg_valid": f"{p['vegetation_p95']['valid_cells']:,}",
        "comparison_rows": "\n".join(
            f"| {k.replace('_', ' ')} | {v:,} |" for k, v in a.items()
        ),
        "quality_rows": "\n".join(
            f"| {k.replace('_', ' ')} | {v:,} |"
            for k, v in m["quality"].items()
            if isinstance(v, int) and not isinstance(v, bool)
        ),
    }
    for name, target in [
        ("index", root/"index.qmd"),
        ("quality", root/"report/quality.qmd"),
    ]:
        text = (root/"docs/report-templates" / f"{name}.qmd.template").read_text(
            encoding="utf-8"
        )
        for key, value in values.items():
            text = text.replace("@" + key + "@", value)
        target.write_text(text, encoding="utf-8", newline="\n")
