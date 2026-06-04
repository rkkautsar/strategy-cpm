"""Sleeve protocol + registry for the LIVE weight-dict combine.

Unifies the duplicated live combine logic in cpm_live.cmd_allocate and
deploy/cf-pages/format_message.py. Scope is the LIVE weight-dict path ONLY:
the dashboard/CLI series-blend math is intentionally left literal (the three
blend sites use three different float-add term orders, and IEEE-754 addition is
not associative, so imposing a canonical order would break golden-master parity).

Registry order is parity-critical: cpm, ndx, val, rpv (matches the existing
live combine loops). Values pass through each compute fn unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class SleeveResult:
    """Normalized live output of one sleeve at a single sig_d. Values unchanged."""
    name: str                 # "cpm" | "ndx" | "val" | "rpv"
    weights: dict             # ticker -> intra-sleeve weight (exact dict the compute fn returned)
    regime: str
    picks: list               # display tickers
    extra: dict = field(default_factory=dict)   # sleeve-specific display bits


@dataclass(frozen=True)
class SleeveSpec:
    name: str                 # cache-key sleeve id; MUST match get_cached_sleeve_weight name
    weight: float             # blend weight (sourced from config)
    label: str                # display label
    live_getter: Callable[[pd.DataFrame, pd.DataFrame, pd.Timestamp], "SleeveResult"]


def _cpm_live(panel: pd.DataFrame, ndx_panel: pd.DataFrame, sig_d: pd.Timestamp) -> SleeveResult:
    from core import get_cached_sleeve_weight
    from cpm_live import compute_live_weights
    w, basket, regime, safe = get_cached_sleeve_weight(
        "cpm", panel, sig_d, compute_live_weights, panel, sig_d)
    return SleeveResult("cpm", w, regime, list(basket) if basket else [],
                        {"safe": safe, "basket": basket})


def _ndx_live(panel: pd.DataFrame, ndx_panel: pd.DataFrame, sig_d: pd.Timestamp) -> SleeveResult:
    from core import get_cached_sleeve_weight
    from ndx_sleeve_live import compute_ndx_weights
    w, regime, diag = get_cached_sleeve_weight(
        "ndx", panel, sig_d, compute_ndx_weights, panel, ndx_panel, sig_d)
    return SleeveResult("ndx", w, regime, diag.get("selected", []), {"diag": diag})


def _rpv_live(panel: pd.DataFrame, ndx_panel: pd.DataFrame, sig_d: pd.Timestamp) -> SleeveResult:
    from core import get_cached_sleeve_weight
    from rpv_live import compute_rpv_weights
    w, regime, diag = get_cached_sleeve_weight(
        "rpv", panel, sig_d, compute_rpv_weights, panel, sig_d)
    return SleeveResult("rpv", w, regime, diag.get("eligible", []), {"diag": diag})


def _val_live(panel: pd.DataFrame, ndx_panel: pd.DataFrame, sig_d: pd.Timestamp) -> SleeveResult:
    from core import cached_value_backtest
    from cpm_live import DEFAULT_CASH
    val_start = max(pd.Timestamp("2010-06-01"), panel.index.min())
    _, history = cached_value_backtest(panel, ndx_panel, val_start, sig_d)
    rec = next((r for r in reversed(history) if r["sig_d"] <= sig_d), None)
    if rec is None:
        return SleeveResult("val", {DEFAULT_CASH: 1.0}, "VAL_NO_SIGNAL", [], {"record": None})
    w = rec.get("weights", {DEFAULT_CASH: 1.0})
    return SleeveResult("val", w, rec.get("regime", "VAL_UNKNOWN"),
                        rec.get("selected", []), {"record": rec})


def live_registry() -> list[SleeveSpec]:
    """Weights read fresh from config (single source). ORDER is parity-critical: cpm, ndx, val, rpv."""
    from config import CPM_WEIGHT, NDX_WEIGHT, VAL_WEIGHT, RPV_WEIGHT
    return [
        SleeveSpec("cpm", CPM_WEIGHT, "CPM sleeve", _cpm_live),
        SleeveSpec("ndx", NDX_WEIGHT, "NDX sleeve", _ndx_live),
        SleeveSpec("val", VAL_WEIGHT, "VAL sleeve", _val_live),
        SleeveSpec("rpv", RPV_WEIGHT, "RPV sleeve", _rpv_live),
    ]


def compute_live_blend(
    panel: pd.DataFrame, ndx_panel: pd.DataFrame, sig_d: pd.Timestamp
) -> tuple[dict[str, float], dict[str, SleeveResult]]:
    """Return (combined: dict, results_by_name: dict[str, SleeveResult]).

    Reproduces the existing two live combine loops byte-for-byte: same per-sleeve
    calls, same iteration order (registry order cpm,ndx,val,rpv), same accumulation
    combined[t] = combined.get(t, 0.0) + w * spec.weight.
    """
    results: dict[str, SleeveResult] = {}
    combined: dict[str, float] = {}
    for spec in live_registry():
        res = spec.live_getter(panel, ndx_panel, sig_d)
        results[spec.name] = res
        for t, w in res.weights.items():
            combined[t] = combined.get(t, 0.0) + w * spec.weight
    return combined, results
