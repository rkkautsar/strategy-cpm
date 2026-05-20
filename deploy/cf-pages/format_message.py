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
from cpm_live import load_panel, compute_target_weights
from bull_qqq_live import compute_bull_qqq_weights, CASH_TICKER
from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel

CPM_WEIGHT = 0.6
BULL_WEIGHT = 0.3
NDX_WEIGHT = 0.1


def fmt_alloc(weights: dict, label: str, sleeve_weight: float = 1.0) -> str:
    items = sorted(weights.items(), key=lambda x: -x[1])
    lines = [f"*{label}*"]
    for ticker, w in items:
        if w > 0.001:
            lines.append(f"`  {ticker:<6}` {w*100*sleeve_weight:>5.1f}%")
    return "\n".join(lines)


def main() -> None:
    panel = load_panel(start=pd.Timestamp("2018-01-01"))
    ndx_panel = load_ndx_panel()
    # Use last completed month-end as signal date
    today = pd.Timestamp.today().normalize()
    prior_me = (today.replace(day=1) - pd.Timedelta(days=1))
    candidates = panel.index[panel.index <= prior_me]
    sig_d = candidates[-1] if len(candidates) > 0 else today

    cpm_w, pair, cpm_regime, safe = compute_target_weights(panel, sig_d)
    bull_w, bull_regime, bull_diag = compute_bull_qqq_weights(panel, sig_d)
    ndx_w, ndx_regime, ndx_diag = compute_ndx_weights(panel, ndx_panel, sig_d)

    # Combined portfolio
    combined: dict[str, float] = {}
    for t, w in cpm_w.items():
        combined[t] = combined.get(t, 0.0) + w * CPM_WEIGHT
    for t, w in bull_w.items():
        combined[t] = combined.get(t, 0.0) + w * BULL_WEIGHT
    for t, w in ndx_w.items():
        combined[t] = combined.get(t, 0.0) + w * NDX_WEIGHT

    parts = []
    parts.append(f"📈 *CPM-BULL-NDX Monthly Signal*")
    parts.append(f"Signal date: `{sig_d.date()}` · Trade T+1 MOC")
    parts.append("")
    parts.append(f"_CPM: {cpm_regime} · BULL: {bull_regime} · NDX: {ndx_regime}_")
    parts.append("")
    parts.append(fmt_alloc(cpm_w, "CPM sleeve (60%)", 0.6))
    parts.append("")
    parts.append(fmt_alloc(bull_w, "BULL-QQQ sleeve (30%)", 0.3))
    parts.append("")
    parts.append(fmt_alloc(ndx_w, "NDX sleeve (10%)", 0.1))
    parts.append("")
    parts.append(fmt_alloc(combined, "Combined portfolio (100%)"))
    parts.append("")
    parts.append("⚠️ Forward Sh 0.90-1.20 (not 1.43 canonical) · MaxDD -15-25% expected")

    print("\n".join(parts))


if __name__ == "__main__":
    main()
