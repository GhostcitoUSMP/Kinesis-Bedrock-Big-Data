import unittest

from detection.detector import detect_anomalies, transaction_metrics, window_start


class DetectorTests(unittest.TestCase):
    def test_window_start_uses_utc_minute(self):
        self.assertEqual(window_start("2010-01-01T00:01:47"), "2010-01-01T00:01:00Z")
        self.assertEqual(window_start("2010-01-01T01:01:47+01:00"), "2010-01-01T00:01:00Z")

    def test_metrics_and_velocity_rule(self):
        events = [
            {"amount": amount, "errors": error}
            for amount, error in [(10, None), (20, "declined"), (-5, None)]
        ]
        metrics = transaction_metrics(events)
        self.assertEqual(metrics["transaction_count"], 3)
        self.assertEqual(metrics["amount_total"], 25)
        self.assertEqual(metrics["amount_max"], 20)
        self.assertEqual(metrics["error_count"], 1)
        self.assertEqual(detect_anomalies({"transaction_count": 4}), [])
        self.assertEqual(len(detect_anomalies({"transaction_count": 5})), 1)


if __name__ == "__main__":
    unittest.main()
