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
    pd.Timestamp("2026-04-30"): {"term": 0.3271466148653894, "credit": -0.8677612228837291, "equity": -1.6717743309962225},
    pd.Timestamp("2026-05-31"): {"term": 0.3757879574525548, "credit": -1.174249318151616, "equity": -1.8027246722706036},
}


def main():
    data_path = os.path.join(REPO_ROOT, "data", "proxy_adjusted_close_daily.csv")
    panel = pd.read_csv(data_path, index_col=0, parse_dates=True)

    weights, regime, diag = compute_rpv_weights(panel, pd.Timestamp("2026-04-30"))

    assert regime == "CASH"
    assert weights == {"SHV": 1.0}
    assert abs(diag["z_scores"]["term"] - 0.327) <= 1e-2
    assert abs(diag["z_scores"]["credit"] - (-0.868)) <= 1e-2
    assert abs(diag["z_scores"]["equity"] - (-1.672)) <= 1e-2

    z = compute_rpv_signals()
    for dt, expected_row in EXPECTED_SIGNALS.items():
        assert dt in z.index
        row = z.loc[dt]
        for key, expected_val in expected_row.items():
            assert abs(row[key] - expected_val) <= 1e-9

    print("PASS: rpv 0a regression")


if __name__ == "__main__":
    main()
