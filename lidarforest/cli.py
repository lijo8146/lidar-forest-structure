import argparse
import json
import os
import tempfile
import urllib.request
from pathlib import Path

from .core import sha256


def download():
    source = json.loads(Path("data/source.json").read_text(encoding="utf-8"))
    out = Path("data/raw/autzen-classified.laz")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        if sha256(out) == source["sha256"]:
            print("Verified cached source.")
            return
        raise ValueError(
            "Cached source hash mismatch. Preserve/investigate before replacing."
        )
    fd, name = tempfile.mkstemp(dir=out.parent, suffix=".part")
    os.close(fd)
    part = Path(name)
    try:
        request = urllib.request.Request(
            source["url"], headers={"User-Agent": "lidar-forest-structure/0.1"}
        )
        with urllib.request.urlopen(request, timeout=120) as r, part.open("wb") as f:
            while block := r.read(1024 * 1024):
                f.write(block)
        if part.stat().st_size != source["bytes"] or sha256(part) != source["sha256"]:
            raise ValueError("Source failed size/SHA-256 verification.")
        part.rename(out)
        print("Downloaded and verified 74 MB example.")
    finally:
        part.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Auditable LiDAR structure workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("download")
    p = sub.add_parser("run")
    p.add_argument("--config", default="config/example.yml")
    p.add_argument("--output", default="data/processed")
    p.add_argument("--report-assets", default="report/assets")
    p = sub.add_parser("validate")
    p.add_argument("output", nargs="?", default="data/processed")
    args = parser.parse_args()
    if args.command == "download":
        download()
    elif args.command == "run":
        from .workflow import run

        print(
            json.dumps(
                run(args.config, args.output, args.report_assets)["quality"], indent=2
            )
        )
    else:
        from .workflow import validate

        m = validate(args.output)
        print(
            f"Validated {m['aoi_points']:,} AOI returns and {len(m['product_sha256'])} hashed products."
        )


if __name__ == "__main__":
    main()
