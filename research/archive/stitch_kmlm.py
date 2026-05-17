"""Build a stitched KMLM daily series: KFA-MLM index (1988-2020) + live KMLM (2020+)."""
import pandas as pd
import numpy as np

# Load KFA-MLM monthly returns
mr = pd.read_csv("/Users/rkautsar/personal/scripts/support/data/kfa_mlm_index_tr_monthly_returns.csv",
                 parse_dates=["date"])
mr = mr.set_index("date")["kfa_mlm_index_total_return"].sort_index()

# Build month-end synthetic index from monthly returns
synthetic_monthly_index = (1.0 + mr).cumprod() * 100.0
print(f"Synthetic monthly index: {mr.index[0].date()} -> {mr.index[-1].date()}, levels {synthetic_monthly_index.iloc[0]:.2f} -> {synthetic_monthly_index.iloc[-1]:.2f}")

# Load existing proxy panel for live KMLM segment
proxy_panel = pd.read_csv("/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv",
                          parse_dates=["Date"], index_col="Date")
live_kmlm = proxy_panel["KMLM"].dropna()
print(f"Live KMLM: {live_kmlm.index[0].date()} -> {live_kmlm.index[-1].date()}, levels {live_kmlm.iloc[0]:.2f} -> {live_kmlm.iloc[-1]:.2f}")

# Splice point: where does live data start, and what's the month-end synthetic index value just before?
splice_date = live_kmlm.index[0]
synthetic_anchor_date = synthetic_monthly_index.index[synthetic_monthly_index.index < splice_date][-1]
synthetic_anchor_value = synthetic_monthly_index.loc[synthetic_anchor_date]
live_anchor_value = live_kmlm.iloc[0]
scale = synthetic_anchor_value / live_anchor_value
print(f"Splice {splice_date.date()}: synthetic anchor {synthetic_anchor_date.date()} = {synthetic_anchor_value:.2f}, live first = {live_anchor_value:.2f}, scale {scale:.4f}")

# Synthetic part scaled to live; live part as-is. Build a daily series for synthetic portion by piecewise constant
# (hold previous month-end value until next month-end), so daily returns are exact monthly returns at month boundaries.
# Daily index from earliest synthetic date to splice_date - 1 day.
daily_idx = pd.date_range(start=synthetic_monthly_index.index[0], end=splice_date - pd.Timedelta(days=1), freq="B")
# For each business day, find latest month-end of synthetic series <= that day
synth_series = synthetic_monthly_index.reindex(daily_idx, method="ffill")
synth_series = synth_series.dropna()  # may have NaN before first month-end
synth_series = synth_series / scale  # scale to live anchor

# Combine
stitched = pd.concat([synth_series, live_kmlm])
stitched = stitched[~stitched.index.duplicated(keep="last")].sort_index()
stitched.name = "KMLM_stitched"
print(f"Stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()}, rows {len(stitched)}")
stitched.to_csv("/tmp/kmlm_stitched_daily.csv", header=True)
print("Wrote /tmp/kmlm_stitched_daily.csv")
