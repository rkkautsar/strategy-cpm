import pandas as pd

from sleeves import compute_live_blend, get_blend_weights
from cpm_live import load_panel, compute_live_weights
from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel
from rpv_live import compute_rpv_weights
from core import get_cached_sleeve_weight, cached_value_backtest


def test_compute_live_blend_parity():
    # Offline/deterministic panel (live=False default; live=True hits yfinance -> flaky).
    # The old-vs-new combine equivalence holds for any panel + sig_d.
    panel = load_panel(start=pd.Timestamp("2010-01-01"))
    ndx_panel = load_ndx_panel()
    sig_d = panel.index[-1]

    # Old-style inline combine (the logic compute_live_blend replaces).
    cpm_w, _, _, _ = get_cached_sleeve_weight("cpm", panel, sig_d, compute_live_weights, panel, sig_d)
    ndx_w, _, _ = get_cached_sleeve_weight("ndx", panel, sig_d, compute_ndx_weights, panel, ndx_panel, sig_d)
    rpv_w, _, _ = get_cached_sleeve_weight("rpv", panel, sig_d, compute_rpv_weights, panel, sig_d)

    val_start = max(pd.Timestamp("2010-06-01"), panel.index.min())
    _, val_hist = cached_value_backtest(panel, ndx_panel, val_start, sig_d)
    val_rec = next((r for r in reversed(val_hist) if r["sig_d"] <= sig_d), None)
    val_w = val_rec.get("weights", {"SHV": 1.0}) if val_rec else {"SHV": 1.0}

    blend_weights = get_blend_weights(sig_d)

    old_combined = {}
    for t, w in cpm_w.items():
        old_combined[t] = old_combined.get(t, 0.0) + w * blend_weights["cpm"]
    for t, w in ndx_w.items():
        old_combined[t] = old_combined.get(t, 0.0) + w * blend_weights["ndx"]
    for t, w in val_w.items():
        old_combined[t] = old_combined.get(t, 0.0) + w * blend_weights["val"]
    for t, w in rpv_w.items():
        old_combined[t] = old_combined.get(t, 0.0) + w * blend_weights["rpv"]

    new_combined, res = compute_live_blend(panel, ndx_panel, sig_d)

    assert set(old_combined.keys()) == set(new_combined.keys())
    for k in old_combined:
        assert abs(old_combined[k] - new_combined[k]) < 1e-12
