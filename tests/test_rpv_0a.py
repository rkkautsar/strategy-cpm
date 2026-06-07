import os
import sys

PROXY = "http://0.0.0.0:9"
for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ[key] = PROXY

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pandas as pd

from rpv_live import compute_rpv_signals, compute_rpv_weights


EXPECTED_SIGNALS = {
    pd.Timestamp("2026-04-30"): {
        "term": 0.32714661486539,
        "igcredit": -0.8677612228837291,
        "equity": -1.6717743309962165,
        "hycredit": -1.191221612355295,
        "realyld": 0.7257710212428491,
    },
    pd.Timestamp("2026-05-31"): {
        "term": 0.37578795745255544,
        "igcredit": -1.174249318151616,
        "equity": -1.8027246722705978,
        "hycredit": float("nan"),
        "realyld": 0.746597516397164,
    },
}


def test_rpv_0a():
    data_path = os.path.join(REPO_ROOT, "data", "proxy_adjusted_close_daily.csv")
    panel = pd.read_csv(data_path, index_col=0, parse_dates=True)

    weights, regime, diag = compute_rpv_weights(panel, pd.Timestamp("2026-04-30"))

    assert regime == "WEIGHTED_GUARDED"
    assert abs(weights.get("TIP", 0.0) - 1.0) <= 1e-12
    assert abs(weights.get("SHV", 0.0) - 0.0) <= 1e-12
    assert abs(diag["z_scores"]["term"] - 0.327) <= 1e-2
    assert abs(diag["z_scores"]["igcredit"] - (-0.868)) <= 1e-2
    assert abs(diag["z_scores"]["equity"] - (-1.672)) <= 1e-2
    assert abs(diag["z_scores"]["hycredit"] - (-1.191)) <= 1e-2
    assert abs(diag["z_scores"]["realyld"] - 0.726) <= 1e-2

    z = compute_rpv_signals()
    assert set(z.columns) == {"term", "igcredit", "equity", "hycredit", "realyld"}
    for dt, expected_row in EXPECTED_SIGNALS.items():
        assert dt in z.index
        row = z.loc[dt]
        for key, expected_val in expected_row.items():
            if pd.isna(expected_val):
                assert pd.isna(row[key])
            else:
                assert abs(row[key] - expected_val) <= 1e-9

    print("PASS: rpv 0a regression")


if __name__ == "__main__":
    test_rpv_0a()
