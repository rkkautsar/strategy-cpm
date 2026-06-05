import numpy as np
import pandas as pd

from sleeve_cache import df_digest


def _sample_df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "SPY": [100.0, 101.5, 102.0, np.nan, 103.25],
            "TIP": [50.0, 50.1, 49.9, 50.2, 50.3],
        },
        index=idx,
    )


def test_df_digest_deterministic():
    df = _sample_df()
    assert df_digest(df) == df_digest(df)
    assert df_digest(df) == df_digest(df.copy())


def test_df_digest_value_sensitive():
    df = _sample_df()
    changed = df.copy()
    changed.iloc[1, 0] = changed.iloc[1, 0] + 1.0
    assert df_digest(df) != df_digest(changed)


def test_df_digest_tiny_float_sensitive():
    df = _sample_df()
    changed = df.copy()
    changed.iloc[2, 1] = changed.iloc[2, 1] + 1e-13
    assert df_digest(df) != df_digest(changed)


def test_df_digest_column_rename_sensitive():
    df = _sample_df()
    renamed = df.rename(columns={"SPY": "QQQ"})
    assert df_digest(df) != df_digest(renamed)


def test_df_digest_nan_stable():
    df = _sample_df()
    with_nans = df.copy()
    with_nans.iloc[3, 0] = np.nan
    same_nans = with_nans.copy()
    assert df_digest(with_nans) == df_digest(same_nans)
