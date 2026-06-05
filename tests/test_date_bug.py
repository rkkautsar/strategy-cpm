import pandas as pd
from dashboard_engine import get_last_finalized_month_cutoff


def test_month_end_date_bug_resolution():
    # April 30, 2026 is a business month-end (BME)
    index = pd.date_range("2026-04-01", "2026-04-30", freq="B")

    # 1. Buggy wall-clock logic simulation:
    # If today is April 30, 2026, wall clock replaces day=1 -> 2026-04-01.
    # April 30 is dropped because 2026-04-30 < 2026-04-01 is False.
    buggy_cutoff = pd.Timestamp("2026-04-30").replace(day=1)
    assert buggy_cutoff == pd.Timestamp("2026-04-01")
    assert not (pd.Timestamp("2026-04-30") < buggy_cutoff)

    # 2. Fixed BME-derived index logic simulation:
    # Our helper returns May 1, 2026 because the month-end date is present in the index.
    fixed_cutoff = get_last_finalized_month_cutoff(index)
    assert fixed_cutoff == pd.Timestamp("2026-05-01")

    # Under fixed cutoff, April 30 is correctly KEPT:
    assert pd.Timestamp("2026-04-30") < fixed_cutoff
