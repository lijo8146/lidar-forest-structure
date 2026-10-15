"""Standard-library-only checks, also usable in report-only publishing."""

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

root = Path(__file__).resolve().parents[1]
site = root / "_site"
m = json.loads((root / "report/assets/run.json").read_text(encoding="utf-8"))
for name in ["products.png", "cross-section.png", "vertical-profile.png"]:
    f = root / "report/assets" / name
    if hashlib.sha256(f.read_bytes()).hexdigest() != m["product_sha256"][name]:
        raise ValueError("Changed figure: " + name)
nb = json.loads((root / "notebooks/01_walkthrough.ipynb").read_text(encoding="utf-8"))
if any(
    c.get("outputs") or c.get("execution_count") is not None
    for c in nb["cells"]
    if c["cell_type"] == "code"
):
    raise ValueError("Notebook source must be clean.")
expected = [
    "index.html",
    "report/methods.html",
    "report/quality.html",
    "report/reproduce.html",
]


class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key not in ["href", "src"] or not value:
                continue
            u = urlsplit(value)
            if u.scheme or u.netloc or not u.path:
                continue
            target = (
                site / unquote(u.path.lstrip("/"))
                if u.path.startswith("/")
                else self.current.parent / unquote(u.path)
            )
            if not target.exists():
                raise ValueError(f"Broken local resource in {self.current}: {value}")


parser = Links()
for name in expected:
    f = site / name
    text = f.read_text(encoding="utf-8")
    if "Traceback (most recent call last)" in text:
        raise ValueError("Embedded execution error.")
    parser.current = f
    parser.feed(text)
if f"{m['aoi_points']:,}" not in (site / "index.html").read_text(encoding="utf-8"):
    raise ValueError("Stale overview statistics.")
if "@aoi_points@" in (root / "index.qmd").read_text(encoding="utf-8"):
    raise ValueError("Unrendered report template.")
print(
    "Report validated: four pages, local resources, figure hashes, current statistics and clean notebook."
)
