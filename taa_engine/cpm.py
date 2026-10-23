from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .data import RISKY_ASSETS, SAFE_ASSETS


TOP_N = 4
TREND_MONTHS = 10
VOL_DAYS = 252
MIN_VARIANCE_HOLDINGS = 3


def _momentum_13612(prices: pd.Series) -> float:
    """Mean of 1, 3, 6, and 12-month simple total returns."""
    if len(prices) < 13:
        return float("nan")
    last = float(prices.iloc[-1])
    horizons = (1, 3, 6, 12)
    return float(np.mean([last / float(prices.iloc[-1 - h]) - 1.0 for h in horizons]))


def _min_variance_trio(
    daily_returns: pd.DataFrame, candidates: list[str], signal_date: pd.Timestamp,
) -> list[str]:
    """Choose the equal-weight trio with the lowest trailing covariance variance."""
    window = daily_returns.loc[:signal_date, candidates].tail(VOL_DAYS)
    if len(window) < VOL_DAYS or window.isna().any().any():
        return candidates[:MIN_VARIANCE_HOLDINGS]

    covariance = window.cov().to_numpy(dtype=float)
    best_names = candidates[:MIN_VARIANCE_HOLDINGS]
    best_variance = float("inf")
    equal_weights = np.full(MIN_VARIANCE_HOLDINGS, 1.0 / MIN_VARIANCE_HOLDINGS)
    for names in combinations(candidates, MIN_VARIANCE_HOLDINGS):
        indices = [candidates.index(name) for name in names]
        matrix = covariance[np.ix_(indices, indices)]
        variance = float(equal_weights @ matrix @ equal_weights)
        if variance < best_variance:
            best_variance = variance
            best_names = list(names)
    return best_names


def cpm_monthly_targets(prices: pd.DataFrame) -> pd.DataFrame:
    """Return target-weight rows on the next trading day after each month end.

    CPM ranks the top four ETFs by 10-month Faber trend distance divided by
    trailing annualized daily volatility. Positive-trend breadth sets the risky
    allocation to 0/0/50/100%. At full breadth, the minimum-variance trio is
    held equally. Any remaining allocation goes to the better of BIL and IEF by
    1/3/6/12-month momentum. No HYG canary is applied.
    """
    required = (*RISKY_ASSETS, *SAFE_ASSETS)
    missing = sorted(set(required) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing CPM price columns: {', '.join(missing)}")

    prices = prices.sort_index()
    monthly = prices.groupby(prices.index.to_period("M")).tail(1)
    daily_returns = prices.pct_change(fill_method=None)
    events = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)

    for month_index, signal_date in enumerate(monthly.index):
        if month_index + 1 >= len(monthly.index):
            break
        if signal_date not in prices.index:
            continue

        monthly_history = monthly.loc[:signal_date]
        if len(monthly_history) < 13:
            continue
        trend = monthly_history.iloc[-1] / monthly_history.tail(TREND_MONTHS).mean() - 1.0
        trailing_returns = daily_returns.loc[:signal_date].tail(VOL_DAYS)
        scores: dict[str, float] = {}
        for ticker in RISKY_ASSETS:
            asset_returns = trailing_returns[ticker].dropna()
            if len(asset_returns) < VOL_DAYS or pd.isna(trend.get(ticker)):
                continue
            annualized_volatility = float(asset_returns.std(ddof=1) * np.sqrt(252))
            if annualized_volatility > 0:
                scores[ticker] = float(trend[ticker]) / annualized_volatility

        if len(scores) < TOP_N:
            continue
        ranked = sorted(scores, key=lambda ticker: scores[ticker], reverse=True)[:TOP_N]
        positive = [ticker for ticker in ranked if trend[ticker] > 0]
        breadth = len(positive)
        risky_fraction = max(0.0, (breadth - 2) / 2.0)

        weights = {ticker: 0.0 for ticker in prices.columns}
        safe_scores = {
            ticker: _momentum_13612(monthly_history[ticker])
            for ticker in SAFE_ASSETS
        }
        safe_asset = max(
            SAFE_ASSETS,
            key=lambda ticker: safe_scores[ticker] if np.isfinite(safe_scores[ticker]) else -np.inf,
        )

        if breadth:
            selected = positive
            if breadth == 4:
                selected = _min_variance_trio(daily_returns, positive, signal_date)
            per_asset_weight = risky_fraction / len(selected)
            for ticker in selected:
                weights[ticker] = per_asset_weight
        weights[safe_asset] += 1.0 - risky_fraction

        signal_position = prices.index.get_loc(signal_date)
        execution_position = signal_position + 1
        if execution_position < len(prices.index):
            execution_date = prices.index[execution_position]
            events.loc[execution_date] = pd.Series(weights)

    return events.dropna(how="all")
