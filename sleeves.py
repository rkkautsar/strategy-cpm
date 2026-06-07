"""Sleeve protocol + blend helpers for live and backtest wiring.

Registry order is parity-critical: cpm, ndx, val, rpv. Values pass through each
sleeve compute fn unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from config import BASE_BLEND_WEIGHTS, SAHM_STRESS_BLEND_WEIGHTS


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


BLEND_SLEEVES: tuple[str, ...] = ("cpm", "ndx", "val", "rpv")


def get_blend_weights(sig_d: pd.Timestamp | None = None) -> dict[str, float]:
    """Return active sleeve blend weights for a signal date.

    sig_d=None keeps base production weights for backward compatibility.
    """
    if sig_d is None:
        return dict(BASE_BLEND_WEIGHTS)

    from data_loader import is_sahm_stress

    if is_sahm_stress(pd.Timestamp(sig_d)):
        return dict(SAHM_STRESS_BLEND_WEIGHTS)
    return dict(BASE_BLEND_WEIGHTS)


def live_registry(sig_d: pd.Timestamp | None = None) -> list[SleeveSpec]:
    """Live sleeve specs with active blend weights. ORDER is parity-critical."""
    weights = get_blend_weights(sig_d)
    return [
        SleeveSpec("cpm", weights["cpm"], "CPM sleeve", _cpm_live),
        SleeveSpec("ndx", weights["ndx"], "NDX sleeve", _ndx_live),
        SleeveSpec("val", weights["val"], "VAL sleeve", _val_live),
        SleeveSpec("rpv", weights["rpv"], "RPV sleeve", _rpv_live),
    ]


def build_blend_weight_schedule(
    index: pd.DatetimeIndex,
    signal_dates: list[pd.Timestamp],
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, list[tuple[pd.Timestamp, float]]]:
    """Build daily T+1 sleeve-blend weights from monthly signal dates.

    Returns (weights_df, turnover_events), where turnover_events contains
    (apply_from, gross_abs_weight_change).
    """
    weights_df = pd.DataFrame(0.0, index=index, columns=list(BLEND_SLEEVES))
    turnover_events: list[tuple[pd.Timestamp, float]] = []
    prev_weights: dict[str, float] = {}

    for i, sig_d in enumerate(signal_dates):
        sig_d = pd.Timestamp(sig_d)
        active_weights = get_blend_weights(sig_d)

        future = index[index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]

        if i + 1 < len(signal_dates):
            next_sig = pd.Timestamp(signal_dates[i + 1])
            next_future = index[index > next_sig]
            end_apply = next_future[0] if len(next_future) >= 1 else (pd.Timestamp(end) + pd.Timedelta(days=1))
        else:
            end_apply = pd.Timestamp(end) + pd.Timedelta(days=1)

        mask = (index >= apply_from) & (index < end_apply)
        for sleeve in BLEND_SLEEVES:
            weights_df.loc[mask, sleeve] = active_weights.get(sleeve, 0.0)

        keys = set(prev_weights) | set(active_weights)
        turnover = sum(abs(active_weights.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in keys)
        turnover_events.append((apply_from, turnover))
        prev_weights = active_weights

    return weights_df, turnover_events


def apply_blend_reallocation_cost(
    blend_returns: pd.Series,
    turnover_events: list[tuple[pd.Timestamp, float]],
    cost_bps: float,
) -> pd.Series:
    """Deduct cross-sleeve reallocation cost at each rebalance apply date."""
    out = blend_returns.copy()
    for apply_from, turnover in turnover_events:
        if apply_from in out.index:
            out.loc[apply_from] -= turnover * cost_bps / 10000.0
    return out


def compute_live_blend(
    panel: pd.DataFrame, ndx_panel: pd.DataFrame, sig_d: pd.Timestamp
) -> tuple[dict[str, float], dict[str, SleeveResult]]:
    """Return (combined: dict, results_by_name: dict[str, SleeveResult]).

    Uses active blend weights for `sig_d` and combines sleeves in registry order.
    """
    results: dict[str, SleeveResult] = {}
    combined: dict[str, float] = {}
    for spec in live_registry(sig_d):
        res = spec.live_getter(panel, ndx_panel, sig_d)
        results[spec.name] = res
        for t, w in res.weights.items():
            combined[t] = combined.get(t, 0.0) + w * spec.weight
    return combined, results
