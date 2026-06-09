import pandas as pd
import pytest

import engine


def _inputs():
    idx = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03"])
    close = pd.DataFrame({"SPY": [100.0, 101.0, 102.0]}, index=idx)
    daily_ret = close.pct_change().fillna(0.0)

    def weight_fn(_):
        return {"SPY": 1.0}

    return close, daily_ret, weight_fn


def test_segment_returns_conv_raises_on_unknown_convention():
    close, daily_ret, weight_fn = _inputs()

    with pytest.raises(ValueError, match="unknown convention"):
        engine._segment_returns_conv(
            close,
            daily_ret,
            weight_fn,
            pd.Timestamp("2020-01-01"),
            pd.Timestamp("2020-02-10"),
            "mooexx",
            10,
        )


@pytest.mark.parametrize("convention", ["moc", "mooex"])
def test_segment_returns_conv_accepts_known_conventions(convention):
    close, daily_ret, weight_fn = _inputs()

    engine._segment_returns_conv(
        close,
        daily_ret,
        weight_fn,
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-02-10"),
        convention,
        10,
    )
