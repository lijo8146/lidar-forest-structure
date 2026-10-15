import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def draw(out, rasters, shape, cfg, points, hag, smrf):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "#faf8f2",
            "axes.facecolor": "#eceee8",
            "axes.titlesize": 11,
        }
    )
    extent = [cfg["bounds"][0], cfg["bounds"][2], cfg["bounds"][1], cfg["bounds"][3]]
    fig, axes = plt.subplots(2, 3, figsize=(13, 8), layout="constrained")
    names = [
        "dtm_provider",
        "surface_height",
        "vegetation_p95",
        "return_density",
        "dtm_difference_smrf_minus_provider",
        "vegetation_return_fraction_above_threshold",
    ]
    titles = [
        "Terrain / supplied ground (m NAVD88)",
        "Surface height / all classes (m)",
        "Vegetation return height / p95 (m)",
        "Retained return density (returns/m²)",
        "Terrain: SMRF minus supplied (m)",
        "Vegetation returns > threshold\n/ valid returns",
    ]
    for ax, name, title in zip(axes.flat, names, titles):
        a = rasters[name][0].reshape(shape)
        kw = {}
        if "difference" in name:
            limit = max(0.1, float(np.nanquantile(np.abs(a), 0.98)))
            kw = {"vmin": -limit, "vmax": limit}
            cmap = "RdBu_r"
        else:
            cmap = "terrain" if name == "dtm_provider" else "viridis"
        if "fraction" in name:
            kw = {"vmin": 0, "vmax": 1}
        im = ax.imshow(a, extent=extent, cmap=cmap, **kw)
        ax.set_title(title)
        ax.ticklabel_format(style="plain", useOffset=False)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        fig.colorbar(
            im, ax=ax, shrink=0.7, extend="both" if "difference" in name else "neither"
        )
    fig.suptitle(
        "250 m woodland/open-space window / Autzen, Oregon\n2 m cells / blanks retain missing support",
        fontsize=16,
    )
    fig.savefig(out / "products.png", dpi=160)
    plt.close(fig)
    mid = (cfg["bounds"][1] + cfg["bounds"][3]) / 2
    strip = np.abs(points["Y"] - mid) < 3
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), layout="constrained")
    for ax, ground, title in zip(
        axes,
        [points["Classification"] == 2, smrf == 2],
        ["Supplied ground labels", "Experimental SMRF ground labels"],
    ):
        for mask, color, label in [
            (~ground, "#8b9b7a", "Other returns"),
            (ground, "#b06e42", "Ground"),
        ]:
            k = strip & mask
            ax.scatter(
                points["X"][k] - cfg["bounds"][0],
                points["Z"][k],
                s=2,
                c=color,
                label=label,
                rasterized=True,
            )
        ax.set(
            title=title,
            xlabel="Distance east from AOI edge (m)",
            ylabel="Elevation (m NAVD88)",
        )
        ax.legend(markerscale=3)
    fig.suptitle("Same 6 m wide cross-section / labels compared, not validated")
    fig.savefig(out / "cross-section.png", dpi=170)
    plt.close(fig)
    veg = np.isin(points["Classification"], cfg["vegetation_classes"]) & np.isfinite(
        hag
    )
    fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
    ax.hist(hag[veg], bins=np.arange(-5, 51, 1), color="#345e50")
    ax.set(
        xlabel="Height above supplied-ground IDW surface (m)",
        ylabel="Vegetation-class returns",
        title="Vertical return profile / not foliage or fuel density",
    )
    ax.axvline(0, c="#b06e42", lw=1)
    fig.savefig(out / "vertical-profile.png", dpi=150)
    plt.close(fig)
