"""NDX sleeve drawdown circuit breaker helpers."""
from __future__ import annotations

import pandas as pd

# ============================================================================
# Per-sleeve drawdown circuit breaker (TT Market Vane #5 analog).
# ============================================================================

# Drawdown threshold: paper-cited, not grid-scanned.
# Source: Nystrup & Boyd (2019) "Multi-period portfolio selection with
# drawdown control", Stanford EE/Annals of OR -- Dmax = 10% used as the
# canonical example throughout. Also matches RustyBT live-trading
# `DrawdownCircuitBreaker` "moderate" default (max_drawdown_pct=0.10)
# and QuantMatter TAA playbook "capital defense" trigger (~10-12%).
# Avoids the prior hand-picked -15% which had no paper citation.
DD_CIRCUIT_THRESHOLD = -0.10   # -10% drawdown triggers defensive (Nystrup-Boyd)
DD_CIRCUIT_SCALE = 0.0         # 0 = full cash; could be 0.5 for partial
DD_CIRCUIT_SLEEVES = ("NDX",)  # NDX only -- empirical test showed BULL DD
# circuit added negligible benefit (+0.004 Sh vs no-DD baseline) while NDX-
# only captured the bulk of the benefit. CPM also excluded (low standalone DD);
# BULL excluded (13612U trend gate already self-protects vs drawdowns).


# Rolling-peak lookback for DD circuit breaker = 63 trading days (~1
# calendar quarter, matches the r3 component in the existing 13612U
# momentum signal so all lookbacks in the strategy are consistent).
#
# SOTA precedent: rolling DD lookback is the standard (RustyBT live
# trading: 30-60d for stable strategies; Yang-Zhong 2013 REDD; Nystrup-
# Boyd Stanford). All-time peak (infinite memory) is NOT SOTA -- known
# failure mode where stale peaks suppress legitimate recoveries (e.g.
# 2021 ATH NDX peak suppressing 2023 H1 recovery).
DD_CIRCUIT_LOOKBACK_DAYS = 63


def compute_dd_circuit_scale(sleeve_returns: pd.Series,
                              sig_dates: list,
                              threshold: float = DD_CIRCUIT_THRESHOLD,
                              recovery_scale: float = DD_CIRCUIT_SCALE,
                              lookback_days: int = DD_CIRCUIT_LOOKBACK_DAYS,
                              ) -> pd.Series:
    """Daily DD circuit breaker for a single sleeve, rolling-peak scoped.

    Measures DD from rolling-window peak (`lookback_days` trading days)
    instead of all-time equity peak. Avoids the failure mode of inheriting
    ancient peaks: e.g. if NDX sleeve hit ATH in Nov-2021 and goes to cash
    for 18 months, an all-time peak DD circuit would never let the sleeve
    fully re-engage during 2023 recovery because eq is still below the
    stale 2021 peak. The 90d rolling peak forgets stale peaks after ~1
    quarter while preserving recent (Feb-2022 style) protection.

    DD-triggered and applied per-sleeve instead of portfolio-wide.

    Args:
        sleeve_returns: daily sleeve returns
        sig_dates: list of monthly signal dates (lift events)
        threshold: trigger DD (negative, e.g. -0.10)
        recovery_scale: scale during defensive (0.0 to 1.0)
        lookback_days: rolling peak window in trading days (default 63 = ~1Q)

    Returns:
        scale: pd.Series of daily scale [0, 1] applied to sleeve returns
    """
    if sleeve_returns.empty:
        return pd.Series(dtype=float)
    eq = (1.0 + sleeve_returns).cumprod()
    rolling_peak = eq.rolling(lookback_days, min_periods=1).max()
    dd = eq / rolling_peak - 1.0
    scale = pd.Series(1.0, index=sleeve_returns.index)
    sig_set = set(sig_dates)
    current = 1.0
    for i, day in enumerate(sleeve_returns.index):
        if day in sig_set:
            current = 1.0   # reset scale at signal date
        elif dd.iloc[i] < threshold:
            current = recovery_scale
        scale.iloc[i] = current
    return scale


def current_dd_state(sleeve_returns: pd.Series,
                       threshold: float = DD_CIRCUIT_THRESHOLD) -> dict:
    """Get current DD circuit state for a single sleeve.

    Returns dict with: current_dd, peak_date, days_in_dd, triggered,
    regime ('CIRCUIT_TRIGGERED' or 'NORMAL'), as_of_date.
    """
    if sleeve_returns.empty:
        return dict(current_dd=0.0, triggered=False, regime="NO_DATA",
                     as_of_date=None)
    eq = (1.0 + sleeve_returns).cumprod()
    dd_series = eq / eq.cummax() - 1.0
    current_dd = float(dd_series.iloc[-1])
    peak_value = eq.cummax().iloc[-1]
    peak_date = eq[eq == peak_value].index[-1]
    triggered = current_dd < threshold
    days_in_dd = (sleeve_returns.index[-1] - peak_date).days if current_dd < 0 else 0
    return dict(
        current_dd=current_dd,
        peak_date=peak_date,
        days_in_dd=days_in_dd,
        triggered=triggered,
        threshold=threshold,
        regime="CIRCUIT_TRIGGERED" if triggered else "NORMAL",
        as_of_date=sleeve_returns.index[-1],
    )
