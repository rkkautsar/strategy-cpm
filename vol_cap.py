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
# NDX-only after the 2026-05-27 execution-day lookahead audit. The same
# audit that caught the DCH20 lookahead also revealed the same bug in the
# sleeve-equity DD-10% circuit (same-day scale application after a same-day
# trigger). With the proper t+1 MOO execution lag now applied in
# compute_dd_circuit_scale below, the BULL DD circuit was found to be net
# Sharpe-negative on the BULL sleeve (0.983 vs 1.023 raw), so BULL was
# dropped from DD_CIRCUIT_SLEEVES. NDX circuit kept: with t+1 lag it is
# Sharpe-neutral (1.010 vs 1.016 raw) but Calmar-positive (0.78 vs 0.64)
# and meaningfully shallower MaxDD (-27.5% vs -43.6% raw). CPM excluded.
# See research/dch_t_plus_1_moo_2026_05.log for the forensic detail.
DD_CIRCUIT_SLEEVES = ("NDX",)


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
    # T+1 MOO execution: when trigger fires at day t close, the defensive
    # scale takes effect STARTING day t+1 (modeling next-day-open trade).
    # Order: set scale[t] = current state FIRST, THEN check trigger to
    # update state for tomorrow. The prior same-day implementation
    # (`scale[t] = 0 immediately on trigger at t close`) was caught
    # 2026-05-27 as an execution-day lookahead during the DCH20 audit:
    # it credited the strategy with avoiding day-t's close-to-close return
    # using information only available at day-t close. NDX DD-10% inflated
    # by ~0.44 Sharpe under same-day; BULL inflated by ~0.10 Sharpe. See
    # research/dch_t_plus_1_moo_2026_05.log.
    for i, day in enumerate(sleeve_returns.index):
        if day in sig_set:
            current = 1.0   # reset scale at signal date (apply on T+1 anyway)
        scale.iloc[i] = current  # set TODAY based on yesterday's trigger state
        if dd.iloc[i] < threshold:
            current = recovery_scale  # trigger fires; defensive STARTING TOMORROW
    return scale


# ============================================================================
# Donchian-20 "STRICT" daily circuit - REMOVED 2026-05-27 (lookahead failure).
#
# The 2026-05-27 attempt to replace BULL's intramonth circuit with a daily
# Donchian-20 "STRICT" rule (latch defensive when asset_price[t] <= rolling
# 20-day low excluding today) appeared to deliver BULL standalone Sharpe
# 1.557-1.608 vs the DD-10%/63d circuit at 1.109. Audits (look-ahead in the
# window definition, sub-period stability, walk-forward, 24y extension,
# DCH-N parameter sweep) all passed superficially and oracle voted swap.
#
# A subsequent critic-prompted execution-day lag test (lag the trigger by
# 1 trading day to model realistic next-day execution) revealed catastrophic
# Sharpe collapse: 1.589 -> 0.899 with 1-day lag, 0.821 with 2-day lag.
# That is, the apparent edge was almost entirely from applying the defensive
# scale on day t's own close-to-close return, which used same-day trigger
# information that could only be acted on at t+1 open.
#
# Excluding today from the rolling LOOKBACK WINDOW (the "STRICT" form) was
# not enough; the SCALE itself needed to be lagged. With proper execution
# lag, the rule was strictly worse than the incumbent DD-10% circuit.
#
# Knowledge-note correction: the "swap when audits pass and floor is bounded"
# orchestrator rule should require an explicit execution-day lag ("shift
# trigger by 1 day, check Sharpe stability") in the audit gate before
# accepting any intramonth-circuit change.
#
# See research/bull_dch_critic_audits_2026_05.log for the full audit.


# ============================================================================
# LQD/IEF credit-spread intramonth circuit (NDX sleeve).
#
# Rule: latch defensive when LQD/IEF ratio < its rolling 50-day SMA.
# LQD = iShares iBoxx $ Investment Grade Corporate Bonds (duration ~8y)
# IEF = iShares 7-10 Year Treasury Bond ETF (duration ~7y)
# Both have similar duration so the ratio cancels out rate-direction moves,
# leaving an approximate credit-spread proxy. Falling ratio = IG corporates
# underperforming Treasuries = credit-spread widening = risk-off.
#
# Window: 50-day SMA (well-known practitioner standard; not paper-cited but
# robust to lag at this lookback per sanity gate).
# Reset: scale = 1.0 at each monthly signal date (same convention as DD circuit).
# Execution: t+1 MOO honest (scale[t] set BEFORE today's trigger evaluation).
#
# Adopted 2026-05-27 after the NDX intramonth canary audit. Winning metric:
# best Calmar (1.30) of all NDX intramonth options tested, shallowest MaxDD
# (-10.17%), lag-robust (+1d sanity gate delta +0.075 = IMPROVES with lag).
# Trade-off vs prior DD-10%/63d: lower CAGR (13.21% vs 21.40% standalone) but
# better Calmar and shallower MaxDD. PROD blend goes 1.384 -> 1.410 Sharpe.
# See research/ndx_lqd_ief_circuit_2026_05.log for full audit.
#
# Method lineage:
#   - LQD/IEF as credit-spread proxy: duration-cancelled ratio is standard in
#     macro practitioner research (no specific paper citation; HYG/IEF and
#     LQD/IEF spread variants are commonly used).
#   - SMA50 crossover: practitioner moving-average filter family
#     (Faber 2007 SSRN TAA uses 10mo SMA on equity; same family).
LQD_IEF_SMA_WINDOW = 50  # SMA lookback for LQD/IEF ratio (trading days)


def compute_lqd_ief_circuit_scale(lqd_price: pd.Series,
                                     ief_price: pd.Series,
                                     sleeve_index: pd.DatetimeIndex,
                                     sig_dates: list,
                                     sma_window: int = LQD_IEF_SMA_WINDOW,
                                     recovery_scale: float = DD_CIRCUIT_SCALE,
                                     ) -> pd.Series:
    """Daily LQD/IEF < SMA intramonth circuit for a single sleeve.

    Latches defensive when ratio = LQD / IEF < ratio.rolling(SMA_WINDOW).mean()
    Releases to 1.0 at each monthly signal date.

    Args:
        lqd_price: daily close of LQD ETF
        ief_price: daily close of IEF ETF
        sleeve_index: daily index over which to produce scale
        sig_dates: monthly signal dates where the latch resets
        sma_window: rolling SMA window in trading days (default 50)
        recovery_scale: scale when latched defensive (default 0.0)

    Returns:
        scale: pd.Series of daily scale [0, 1] indexed by sleeve_index
    """
    if len(sleeve_index) == 0:
        return pd.Series(dtype=float)
    lqd = lqd_price.reindex(sleeve_index).ffill()
    ief = ief_price.reindex(sleeve_index).ffill()
    ratio = lqd / ief
    sma = ratio.rolling(sma_window).mean()
    trigger = (ratio < sma) & ratio.notna() & sma.notna()
    scale = pd.Series(1.0, index=sleeve_index)
    sig_set = set(sig_dates)
    state = 1.0
    # T+1 MOO honest execution: set scale[t] FIRST, then check trigger to
    # update state for t+1. Trigger evaluated at day-t close fires defensive
    # starting day t+1.
    for i, day in enumerate(sleeve_index):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        if bool(trigger.iloc[i]):
            state = recovery_scale
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
