#!/usr/bin/env python
"""Format the monthly signal as a clean Markdown message for Telegram/Discord/email.

Reads from cpm_live.py allocate output and produces a compact, mobile-friendly
formatted message.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import cpm_live as cpm
from cpm_live import load_panel, compute_live_weights
from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel
from rpv_live import compute_rpv_weights
from value_sleeve_live import cached_value_backtest

CPM_WEIGHT = 0.60
NDX_WEIGHT = 0.15
VAL_WEIGHT = 0.15
RPV_WEIGHT = 0.10


def fmt_alloc(weights: dict, label: str, sleeve_weight: float = 1.0) -> str:
    items = sorted(weights.items(), key=lambda x: -x[1])
    lines = [f"*{label}*"]
    for ticker, w in items:
        if w > 0.001:
            lines.append(f"`  {ticker:<6}` {w*100*sleeve_weight:>5.1f}%")
    return "\n".join(lines)


def main() -> None:
    panel = load_panel(live=True)
    ndx_panel = load_ndx_panel()
    # Use last completed month-end as signal date
    today = pd.Timestamp.today().normalize()
    prior_me = (today.replace(day=1) - pd.Timedelta(days=1))
    candidates = panel.index[panel.index <= prior_me]
    sig_d = candidates[-1] if len(candidates) > 0 else today

    from value_sleeve_live import get_cached_sleeve_weight
    cpm_w, pair, cpm_regime, safe = get_cached_sleeve_weight(
        "cpm", panel, sig_d, compute_live_weights, panel, sig_d
    )
    ndx_w, ndx_regime, ndx_diag = get_cached_sleeve_weight(
        "ndx", panel, sig_d, compute_ndx_weights, panel, ndx_panel, sig_d
    )
    rpv_w, rpv_regime, rpv_diag = get_cached_sleeve_weight(
        "rpv", panel, sig_d, compute_rpv_weights, panel, sig_d
    )

    # VAL is stateful: derive current live weights from full history run.
    val_start = max(pd.Timestamp("2010-06-01"), panel.index.min())
    _, val_hist = cached_value_backtest(panel, ndx_panel, val_start, sig_d)
    val_rec = next((r for r in reversed(val_hist) if r["sig_d"] <= sig_d), None)
    if val_rec is None:
        val_w = {"SHV": 1.0}
        val_regime = "VAL_NO_SIGNAL"
        val_picks: list[str] = []
    else:
        val_w = val_rec.get("weights", {"SHV": 1.0})
        val_regime = val_rec.get("regime", "VAL_UNKNOWN")
        val_picks = val_rec.get("selected", [])

    # Combined portfolio
    combined: dict[str, float] = {}
    for t, w in cpm_w.items():
        combined[t] = combined.get(t, 0.0) + w * CPM_WEIGHT
    for t, w in ndx_w.items():
        combined[t] = combined.get(t, 0.0) + w * NDX_WEIGHT
    for t, w in val_w.items():
        combined[t] = combined.get(t, 0.0) + w * VAL_WEIGHT
    for t, w in rpv_w.items():
        combined[t] = combined.get(t, 0.0) + w * RPV_WEIGHT

    parts = []
    parts.append(f"📈 *CPM-NDX-VAL-RPV Monthly Signal*")
    parts.append(f"Signal date: `{sig_d.date()}` · Trade T+1 OPEN (MOO)")
    parts.append("")
    parts.append(f"_CPM: {cpm_regime} · NDX: {ndx_regime} · VAL: {val_regime} · RPV: {rpv_regime}_")
    if val_picks:
        parts.append(f"_VAL picks: {', '.join(val_picks)}_")
    parts.append("")
    parts.append(fmt_alloc(cpm_w, "CPM sleeve (60%)", CPM_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(ndx_w, "NDX sleeve (15%)", NDX_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(val_w, "VAL sleeve (15%)", VAL_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(rpv_w, "RPV sleeve (10%)", RPV_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(combined, "Combined portfolio (100%)"))
    parts.append("")
    parts.append("⚠️ Backtest only · see dashboard caveats before trading")

    print("\n".join(parts))


if __name__ == "__main__":
    main()
