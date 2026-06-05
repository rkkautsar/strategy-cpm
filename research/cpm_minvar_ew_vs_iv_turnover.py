# -*- coding: utf-8 -*-
"""Focused: min-var 3-of-4 subset (current prod selection) EW vs inverse-vol,
HEADLINE = annualized one-way turnover (stability argument), plus full metric
table + per-crisis MaxDD + IV-vs-EW significance reproduce.

SAME selection (ewobj min-var subset = current prod), differ only in sizing:
  MINVAR_IV   = ewobj min-var subset + inverse-vol  (= current prod)
  COHERENT_EW = ewobj min-var subset + equal-weight

Read-only re prod. No prod/memo/cpm_live edits. No commit.
Run: .venv/bin/python -m research.cpm_minvar_ew_vs_iv_turnover
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from research import cpm_harness as H
from research.cpm_minvar_coherence import make_weight_fn
from research.cpm_weighting_corr import CRISES, annualized_turnover
from research.cpm_bootstrap_multimetric import (
    paired_block_bootstrap_mm, _sortino_ann, _cvar_ratio_ann,
)

OUT_JSON = Path(__file__).resolve().parent / "cpm_minvar_ew_vs_iv_turnover_findings.json"


def full_metrics(returns, data):
    m = H.metrics(returns, data=data)  # Sharpe Calmar Martin MaxDD CAGR vol
    x = returns.values
    m["Sortino"] = _sortino_ann(x, None)
    m["CVaR_ratio"] = _cvar_ratio_ann(x)
    return m


def crisis_maxdd(returns, data):
    out = {}
    for name, (a, b) in CRISES.items():
        r = returns.loc[(returns.index >= a) & (returns.index <= b)]
        if len(r) < 5:
            out[name] = None
            continue
        mm = H._cpm_perf(r, data) if hasattr(H, "_cpm_perf") else None
        import cpm_live
        pm = cpm_live.perf_metrics(r, data.cash)
        out[name] = {"MaxDD": pm.get("max_drawdown"), "Sharpe": pm.get("sharpe")}
    return out


def build_cell(sizing, data, label):
    wf = make_weight_fn(selection="minvar_ewobj", sizing=sizing)
    out = {"label": label}
    for win in ("clean", "ext"):
        r = H.run_strategy(wf, window=win, data=data)
        out[win] = full_metrics(r, data)
        out[win + "_returns"] = r
    out["turnover_ann"] = annualized_turnover(wf, data)
    out["crisis_maxdd"] = crisis_maxdd(out["ext_returns"], data)
    return out


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items()
                          if k in ("Sharpe", "MaxDD", "Calmar")})

    iv = build_cell("invvol", data, "MINVAR_IV (ewobj subset + inverse-vol = PROD)")
    ew = build_cell("ew", data, "COHERENT_EW (ewobj subset + equal-weight)")

    # IV-vs-EW significance reproduce: positive = EW - IV
    bs = paired_block_bootstrap_mm(
        ew["clean_returns"], iv["clean_returns"], data.cash, B=2000, block=21, seed=42
    )

    res = {
        "anchor": {k: float(v) for k, v in anchor.items()},
        "MINVAR_IV": {k: v for k, v in iv.items() if not k.endswith("_returns")},
        "COHERENT_EW": {k: v for k, v in ew.items() if not k.endswith("_returns")},
        "ew_minus_iv_bootstrap_clean": bs,
        "turnover_delta": {
            "iv": iv["turnover_ann"],
            "ew": ew["turnover_ann"],
            "ew_minus_iv": ew["turnover_ann"] - iv["turnover_ann"],
            "pct_lower": (iv["turnover_ann"] - ew["turnover_ann"]) / iv["turnover_ann"]
            if iv["turnover_ann"] else None,
        },
    }
    OUT_JSON.write_text(json.dumps(res, indent=2, default=float))
    print("WROTE", OUT_JSON)
    print(json.dumps(res["turnover_delta"], indent=2, default=float))
    return res


if __name__ == "__main__":
    main()
