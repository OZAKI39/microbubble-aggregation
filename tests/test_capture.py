import unittest
import numpy as np
from microbubble.analysis import capture


class CaptureTests(unittest.TestCase):
    def test_right_censor_does_not_extrapolate(self):
        t = np.linspace(0, 0.02, 21)
        x = np.zeros((21, 1, 3))
        x[:, 0, 0] = 40e-6
        r = capture(t, x, [0])[0]
        self.assertTrue(r["right_censored"])
        self.assertIsNone(r["first_entry_s"])

    def test_hold_and_reexit(self):
        t = np.linspace(0, 0.03, 31)
        x = np.zeros((31, 1, 3))
        x[:, 0, 0] = 40e-6
        x[5:21, 0, 0] = 10e-6
        r = capture(t, x, [0])[0]
        self.assertFalse(r["right_censored"])
        self.assertTrue(r["reexit"])
        self.assertAlmostEqual(r["first_held_entry_s"], 0.005)

    def test_short_entry_is_not_capture(self):
        t = np.linspace(0, 0.02, 21)
        x = np.zeros((21, 1, 3))
        x[:, 0, 0] = 40e-6
        x[-4:, 0, 0] = 10e-6
        r = capture(t, x, [0])[0]
        self.assertTrue(r["right_censored"])
        self.assertIsNotNone(r["first_entry_s"])

    def test_band_hopping_breaks_hold(self):
        t = np.arange(11) * 0.001
        x = np.zeros((11, 1, 3))
        x[5:, 0, 0] = 100e-6
        r = capture(t, x, [0, 100e-6], hold=0.008)[0]
        self.assertTrue(r["right_censored"])

    def test_initial_capture_is_labeled_zero(self):
        t = np.linspace(0, 0.02, 21)
        x = np.zeros((21, 1, 3))
        r = capture(t, x, [0])[0]
        self.assertEqual(r["first_entry_s"], 0.0)
        self.assertFalse(r["right_censored"])


if __name__ == "__main__":
    unittest.main()


class SharedTimeTests(unittest.TestCase):
    def test_contact_raw_nodes_recover_nonaligned_dense_samples(self):
        import h5py, tempfile
        from pathlib import Path
        from microbubble.analysis import aligned

        with (
            tempfile.TemporaryDirectory() as d,
            h5py.File(Path(d) / "a.h5", "w") as h,
            h5py.File(Path(d) / "b.h5", "w") as z,
        ):
            t = np.arange(2001) * 1e-6
            xx = np.zeros((len(t), 2, 3))
            xx[:, 0, 0] = t
            h["time_s"] = t
            h["positions_m"] = xx
            z["time_s"] = t
            z["positions_m"] = xx
            z["sample_time_s"] = np.linspace(0, 0.002, 400)
            z["sample_positions_m"] = np.zeros((400, 2, 3))
            tt, a, b, m = aligned(h, z)
            self.assertEqual(m["LF_source"], "time_s")
            self.assertGreater(len(tt), 100)
            np.testing.assert_array_equal(a, b)
