import tempfile
import unittest
from pathlib import Path

import laspy
import numpy as np
from pyproj import CRS

from lidarforest.workflow import ingest, run


class IngestionTests(unittest.TestCase):
    def make_sample(self, path):
        h = laspy.LasHeader(point_format=7, version="1.4")
        h.add_crs(CRS.from_user_input("EPSG:26910+5703"))
        h.offsets = [494600, 4877700, 0]
        h.scales = [0.001, 0.001, 0.001]
        a = laspy.LasData(h)
        a.x = np.array([494601, 494602, 494603, 494604, 494900])
        a.y = np.full(5, 4877701)
        a.z = np.array([100, 101, 102, 103, 104])
        a.classification = [2, 7, 2, 5, 2]
        a.withheld = [False, False, True, False, False]
        a.return_number = [1] * 5
        a.number_of_returns = [1] * 5
        a.write(path)

    def test_las_and_laz_match_and_filter_flags(self):
        cfg = {
            "bounds": [494600, 4877700, 494610, 4877710],
            "buffer_m": 0,
            "target_crs": "EPSG:26910",
            "vertical_reference": "NAVD88",
            "max_points": 10,
        }
        with tempfile.TemporaryDirectory() as tmp:
            results = []
            for ext in ["las", "laz"]:
                f = Path(tmp) / ("sample." + ext)
                self.make_sample(f)
                a, m = ingest(f, cfg)
                self.assertEqual(m["source_points"], 5)
                self.assertEqual(m["buffered_points_before_filter"], 4)
                self.assertEqual(m["excluded_flagged_or_nonfinite"], 2)
                self.assertEqual(len(a), 2)
                np.testing.assert_array_equal(a["Classification"], [2, 5])
                results.append(a)
            np.testing.assert_array_equal(*results)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "products"
            out.mkdir()
            marker = out / "keep.txt"
            marker.write_text("keep")
            with self.assertRaisesRegex(ValueError, "exists"):
                run(output=out)
            self.assertEqual(marker.read_text(), "keep")
