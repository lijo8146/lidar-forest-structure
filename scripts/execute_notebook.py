import json
import os
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

root = Path(__file__).resolve().parents[1]
kernel = root / "work/jupyter/kernels/lidar-local"
kernel.mkdir(parents=True, exist_ok=True)
(kernel / "kernel.json").write_text(
    json.dumps(
        {
            "argv": [
                sys.executable,
                "-m",
                "ipykernel_launcher",
                "-f",
                "{connection_file}",
            ],
            "display_name": "LiDAR local",
            "language": "python",
        }
    ),
    encoding="utf-8",
)
os.environ["JUPYTER_PATH"] = (
    str(root / "work/jupyter") + os.pathsep + os.environ.get("JUPYTER_PATH", "")
)
nb = nbformat.read(root / "notebooks/01_walkthrough.ipynb", as_version=4)
NotebookClient(
    nb,
    timeout=180,
    kernel_name="lidar-local",
    resources={"metadata": {"path": str(root)}},
).execute()
nbformat.write(nb, root / "work/01_walkthrough.executed.ipynb")
print("Walkthrough executed; source outputs remain clean.")
