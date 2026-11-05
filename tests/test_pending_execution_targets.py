import unittest

import numpy as np
import pandas as pd

from taa_engine.cpm import cpm_monthly_targets
from taa_engine.data import RISKY_ASSETS, SAFE_ASSETS
from taa_engine.strategies import _events_from_signals


class PendingExecutionTargetTests(unittest.TestCase):
    def test_pending_date_emits_only_latest_month_signal_beyond_price_history(self):
        prices = pd.DataFrame(
            {"A": [100.0, 101.0, 102.0], "B": [100.0, 99.0, 98.0]},
            index=pd.to_datetime(["2025-01-31", "2025-02-03", "2025-02-28"]),
        )
        signals = [
            (pd.Timestamp("2025-01-31"), {"A": 1.0}),
            (pd.Timestamp("2025-02-28"), {"B": 1.0}),
        ]

        actual = _events_from_signals(
            prices, signals, pending_execution_date=pd.Timestamp("2025-03-05"),
        )

        self.assertEqual(list(actual.index), [pd.Timestamp("2025-02-03"), pd.Timestamp("2025-03-05")])
        self.assertEqual(actual.loc[pd.Timestamp("2025-02-03"), "A"], 1.0)
        self.assertEqual(actual.loc[pd.Timestamp("2025-03-05"), "B"], 1.0)

    def test_pending_date_does_not_relabel_an_older_signal(self):
        prices = pd.DataFrame(
            {"A": [100.0, 101.0, 102.0]},
            index=pd.to_datetime(["2025-01-31", "2025-02-03", "2025-02-28"]),
        )
        signals = [(pd.Timestamp("2025-01-31"), {"A": 1.0})]

        actual = _events_from_signals(
            prices, signals, pending_execution_date=pd.Timestamp("2025-03-03"),
        )

        self.assertEqual(list(actual.index), [pd.Timestamp("2025-02-03")])

    def test_cpm_pending_row_preserves_existing_backtest_events(self):
        index = pd.bdate_range("2020-01-01", "2022-02-28")
        columns = (*RISKY_ASSETS, *SAFE_ASSETS)
        t = np.arange(len(index), dtype=float)
        prices = pd.DataFrame(
            {
                ticker: 100 * np.exp((0.00015 + position * 0.00001) * t + 0.004 * np.sin(t / (17 + position)))
                for position, ticker in enumerate(columns)
            },
            index=index,
        )
        regular = cpm_monthly_targets(prices)
        pending_date = index[-1] + pd.offsets.BDay(1)
        with_pending = cpm_monthly_targets(prices, pending_execution_date=pending_date)

        self.assertIn(pending_date, with_pending.index)
        pd.testing.assert_frame_equal(with_pending.drop(index=pending_date), regular)


if __name__ == "__main__":
    unittest.main()
