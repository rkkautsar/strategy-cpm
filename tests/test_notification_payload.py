import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from taa_engine.dashboard import build_dashboard


class NotificationPayloadTests(unittest.TestCase):
    def test_pending_target_is_in_email_and_dashboard(self):
        dates = pd.to_datetime(["2026-09-01", "2026-10-30"])
        prices = pd.DataFrame({"SPY": [100.0, 102.0]}, index=dates)
        historical = pd.DataFrame({"SPY": [1.0]}, index=[dates[0]])
        pending = pd.concat([historical, pd.DataFrame({"SPY": [0.5], "BIL": [0.5]}, index=[pd.Timestamp("2026-11-02")])]).fillna(0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.html"
            build_dashboard(prices=prices, strategy_targets={"CPM": historical},
                            portfolios={"CPM": pd.Series([100.0, 102.0], index=dates)},
                            metrics=pd.DataFrame(), output_path=output, fee_bps=10,
                            rebalance_dates=list(historical.index), notification_targets={"CPM": pending})
            notification = json.loads((output.parent / "notification_data.json").read_text())
            dashboard_file = next(output.parent.glob("dashboard-data-*.json"))
            dashboard = json.loads(dashboard_file.read_text())
        self.assertEqual(notification["allocation_month"], "2026-11")
        self.assertEqual(notification["targets"]["CPM"]["current"], {"SPY": 0.5, "BIL": 0.5})
        self.assertEqual(notification["targets"]["CPM"]["current_date"], "2026-11-02")
        self.assertEqual(dashboard["targets"]["CPM"]["current"], {"SPY": 0.5, "BIL": 0.5})
        self.assertEqual(dashboard["rebalance_dates"], ["2026-09-01"])


if __name__ == "__main__":
    unittest.main()
