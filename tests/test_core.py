import tempfile
import unittest
from pathlib import Path

import numpy as np

from lidarforest.core import (
    cell_index,
    coordinate_plan,
    grid,
    maximum,
    quantile,
    sha256,
    terrain,
)


class CoordinateTests(unittest.TestCase):
    def test_distinct_horizontal_and_vertical_feet(self):
        t, f, _m = coordinate_plan("EPSG:2992+6360", "EPSG:26910", "NAVD88")
        self.assertAlmostEqual(f, 1200 / 3937, 12)
        self.assertNotEqual(f, 0.3048)
        x, y = t.transform(637000, 850000)
        self.assertTrue(493000 < x < 496000 and 4876000 < y < 4880000)
        np.testing.assert_allclose(
            t.transform(x, y, direction="INVERSE"), [637000, 850000], atol=0.0001
        )

    def test_missing_crs_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing"):
            coordinate_plan(None, "EPSG:26910", "NAVD88")

    def test_missing_vertical_rejected(self):
        with self.assertRaisesRegex(ValueError, "vertical"):
            coordinate_plan("EPSG:2992", "EPSG:26910", "NAVD88")

    def test_degrees_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "metres"):
            coordinate_plan("EPSG:2992+6360", "EPSG:4326", "NAVD88")

    def test_unreviewed_datum_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "datum change"):
            coordinate_plan("EPSG:2992+6360", "EPSG:32610", "NAVD88")

    def test_vertical_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "Vertical reference"):
            coordinate_plan("EPSG:2992+6360", "EPSG:26910", "EGM96")


class SurfaceTests(unittest.TestCase):
    def test_grid_orientation_and_half_open_edges(self):
        q, shape, _t = grid([0, 0, 4, 4], 2)
        np.testing.assert_array_equal(q, [[1, 3], [3, 3], [1, 1], [3, 1]])
        keep, idx = cell_index(
            [0, 4, 1, 3, -1], [0, 2, 3, 1, 2], [0, 0, 4, 4], 2, shape
        )
        np.testing.assert_array_equal(keep, [True, False, True, True, False])
        np.testing.assert_array_equal(idx, [2, 0, 3])

    def test_invalid_or_misaligned_grid_rejected(self):
        for bounds, res in [([0, 0, 3, 3], 2), ([0, 0, 4, 4], 0), ([4, 0, 0, 4], 1)]:
            with self.assertRaises(ValueError):
                grid(bounds, res)

    def test_symmetric_plane_center_and_missing_support(self):
        xy = np.array([[0, 0], [2, 0], [0, 2], [2, 2]])
        z = 3 * xy[:, 0] + xy[:, 1] + 10
        values, n, dist = terrain(xy, z, [[1, 1], [100, 100]], radius=3, k=4)
        self.assertAlmostEqual(values[0], 14)
        self.assertTrue(np.isnan(values[1]))
        np.testing.assert_array_equal(n, [4, 0])
        self.assertTrue(np.isinf(dist[1]))

    def test_exact_ground_point_retains_height(self):
        a, _, _ = terrain([[0, 0], [1, 0], [0, 1]], [10, 11, 12], [[0, 0]], k=3)
        self.assertAlmostEqual(a[0], 10)

    def test_no_ground_rejected(self):
        with self.assertRaises(ValueError):
            terrain([[0, 0]], [1], [[0, 0]])

    def test_surface_and_quantile_preserve_empty_cells(self):
        a = maximum([12, 18, 15], [0, 0, 1], 3)
        np.testing.assert_allclose(a[:2], [18, 15])
        self.assertTrue(np.isnan(a[2]))
        q = quantile(np.array([1.0, 3.0]), np.array([0, 0]), 2)
        self.assertAlmostEqual(q[0], 2.9)
        self.assertTrue(np.isnan(q[1]))

    def test_digest_detects_byte_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a"
            p.write_bytes(b"a\n")
            old = sha256(p)
            p.write_bytes(b"a\r\n")
            self.assertNotEqual(old, sha256(p))


class PdalTests(unittest.TestCase):
    def test_smrf_flat_ground_with_elevated_object(self):
        from lidarforest.workflow import classify

        x, y = np.meshgrid(np.arange(20.0), np.arange(20.0))
        a = np.zeros(
            409,
            dtype=[
                ("X", "f8"),
                ("Y", "f8"),
                ("Z", "f8"),
                ("Classification", "u1"),
                ("ReturnNumber", "u1"),
                ("NumberOfReturns", "u1"),
            ],
        )
        a["X"][:400] = x.ravel()
        a["Y"][:400] = y.ravel()
        a["Z"][:400] = 100
        a["X"][400:] = np.tile([8.0, 9.0, 10.0], 3)
        a["Y"][400:] = np.repeat([8.0, 9.0, 10.0], 3)
        a["Z"][400:] = 110
        a["ReturnNumber"] = 1
        a["NumberOfReturns"] = 1
        with tempfile.TemporaryDirectory() as tmp:
            b = classify(
                a,
                {
                    "cell": 1.0,
                    "slope": 0.2,
                    "threshold": 0.45,
                    "scalar": 1.2,
                    "window": 8.0,
                },
                Path(tmp),
            )
            self.assertGreater(np.count_nonzero(b["Classification"][:400] == 2), 380)
            self.assertTrue(np.all(b["Classification"][400:] != 2))


if __name__ == "__main__":
    unittest.main()
