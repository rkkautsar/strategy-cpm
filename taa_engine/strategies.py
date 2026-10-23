from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


HAA_OFFENSIVE = ("SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT")
HAA_SAFE = ("BIL", "IEF")
AAA_UNIVERSE = ("SPY", "EZU", "EWJ", "EEM", "IYR", "RWX", "IEF", "TLT", "DBC", "GLD")
BAA_CANARIES = ("SPY", "VEA", "VWO", "BND")
BAA_OFFENSIVE = ("SPY", "QQQ", "IWM", "VGK", "EWJ", "VWO", "VNQ", "DBC", "GLD", "TLT", "HYG", "LQD")
BAA_DEFENSIVE = ("TIP", "DBC", "BIL", "IEF", "TLT", "LQD", "BND")
VAA_G12_OFFENSIVE = ("SPY", "IWM", "QQQ", "VGK", "EWJ", "EEM", "VNQ", "GSG", "GLD", "TLT", "HYG", "LQD")
VAA_G12_DEFENSIVE = ("SHY", "IEF", "LQD")
NDX_SAFE = ("BIL", "IEF")
NDX_TOP_K = 5


def _month_ends(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.groupby(prices.index.to_period("M")).tail(1)


def _momentum(monthly: pd.DataFrame, ticker: str, weighted: bool = False) -> float:
    if ticker not in monthly or len(monthly) < 13:
        return float("nan")
    series = monthly[ticker].dropna()
    if len(series) < 13:
        return float("nan")
    current = float(series.iloc[-1])
    returns = {months: current / float(series.iloc[-1 - months]) - 1.0 for months in (1, 3, 6, 12)}
    if weighted:
        return (12 * returns[1] + 4 * returns[3] + 2 * returns[6] + returns[12]) / 4.0
    return float(np.mean(list(returns.values())))


def _sma12_relative(monthly: pd.DataFrame, ticker: str) -> float:
    if ticker not in monthly:
        return float("nan")
    series = monthly[ticker].dropna()
    if len(series) < 13:
        return float("nan")
    return float(series.iloc[-1] / series.iloc[-13:].mean() - 1.0)


def _best_safe(monthly: pd.DataFrame, pool: tuple[str, ...]) -> str:
    scores = {ticker: _momentum(monthly, ticker) for ticker in pool}
    valid = {ticker: score for ticker, score in scores.items() if np.isfinite(score)}
    return max(valid, key=valid.get) if valid else pool[0]


def _events_from_signals(prices: pd.DataFrame, signal_weights: list[tuple[pd.Timestamp, dict[str, float]]]) -> pd.DataFrame:
    events = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    for signal_date, weights in signal_weights:
        signal_position = prices.index.get_indexer([signal_date])[0]
        execution_position = signal_position + 1
        if execution_position < len(prices.index):
            events.iloc[execution_position] = 0.0
            for ticker, weight in weights.items():
                events.iat[execution_position, events.columns.get_loc(ticker)] = weight
    return events.dropna(how="all")


def ndx_monthly_targets(etf_prices: pd.DataFrame, constituent_prices: pd.DataFrame) -> pd.DataFrame:
    """NDX stock-momentum sleeve with PIT membership and TIP/SPY/volatility gate.

    On gate-off months, hold the better 13612U asset from BIL/IEF. When on,
    select up to five positive 13612U constituents at 20% each; unused slots
    remain in that same safe asset. Targets execute on the next trading close,
    matching the rest of this engine.
    """
    try:
        import index_constitution as ic
    except ImportError as exc:
        raise RuntimeError("NDX requires index-constitution; install project dependencies with `uv sync`.") from exc
    required = (*NDX_SAFE, "TIP", "SPY")
    missing = sorted(set(required) - set(etf_prices.columns))
    if missing:
        raise ValueError(f"Missing NDX gate/safe ETF prices: {', '.join(missing)}")
    etf_prices = etf_prices.sort_index()
    constituent_prices = constituent_prices.sort_index()
    monthly = _month_ends(etf_prices)
    stock_monthly = _month_ends(constituent_prices)
    spy_returns = etf_prices["SPY"].pct_change(fill_method=None).dropna()
    signals: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for date in monthly.index:
        history = monthly.loc[:date]
        if len(history) < 13:
            continue
        safe = _best_safe(history, NDX_SAFE)
        tip_ok = _momentum(history, "TIP") > 0
        spy_ok = _momentum(history, "SPY") > 0
        vol_history = spy_returns.loc[:date]
        vol_ok = True if len(vol_history) < 252 else vol_history.tail(20).std() < vol_history.tail(252).std()
        if not (tip_ok and spy_ok and vol_ok):
            signals.append((date, {safe: 1.0}))
            continue
        pit = ic.constituents_at("nasdaq100", date.strftime("%Y-%m-%d"))
        members = set(map(str, pit["symbol"].dropna().unique()))
        candidates: dict[str, float] = {}
        for ticker in members.intersection(stock_monthly.columns):
            series = stock_monthly.loc[:date, ticker].dropna()
            if len(series) < 13:
                continue
            score = _momentum(stock_monthly.loc[:date, [ticker]], ticker)
            if np.isfinite(score) and score > 0:
                candidates[ticker] = score
        selected = sorted(candidates, key=candidates.get, reverse=True)[:NDX_TOP_K]
        weights = {ticker: 1.0 / NDX_TOP_K for ticker in selected}
        weights[safe] = weights.get(safe, 0.0) + (NDX_TOP_K - len(selected)) / NDX_TOP_K
        signals.append((date, weights))
    stock_prices = constituent_prices.reindex(etf_prices.index).ffill()
    combined = pd.concat([etf_prices, stock_prices], axis=1)
    combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]
    return _events_from_signals(combined, signals)


def ndx_backtest_inputs(
    etf_prices: pd.DataFrame,
    constituent_prices: pd.DataFrame,
    target_events: pd.DataFrame,
    *,
    delisting_haircut: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return aligned NDX targets/prices, liquidating held names on delisting.

    A first missing close immediately after a valid close is treated as a
    delisting: realize a one-time haircut and move that target slot to the
    currently held safe asset, or BIL if the portfolio had no safe holding.
    """
    stock_prices = constituent_prices.reindex(etf_prices.index)
    stock_prices = stock_prices.ffill()
    prices = pd.concat([etf_prices, stock_prices], axis=1)
    prices = prices.loc[:, ~prices.columns.duplicated(keep="first")].copy()
    events = target_events.reindex(index=etf_prices.index).reindex(columns=prices.columns).copy()
    raw = constituent_prices.reindex(etf_prices.index)
    prior_targets: dict[str, float] = {"BIL": 1.0}
    for position, date in enumerate(etf_prices.index):
        if date in target_events.index:
            row = target_events.loc[date].dropna()
            prior_targets = {str(asset): float(weight) for asset, weight in row.items() if float(weight) > 1e-10}
        if position == 0:
            continue
        previous_date = etf_prices.index[position - 1]
        for asset, weight in list(prior_targets.items()):
            if asset not in raw.columns or asset in NDX_SAFE:
                continue
            if pd.notna(raw.at[previous_date, asset]) and pd.isna(raw.at[date, asset]):
                previous_price = prices.at[previous_date, asset]
                if pd.isna(previous_price) or previous_price <= 0:
                    continue
                liquidation_price = float(previous_price) * (1.0 - delisting_haircut)
                missing_dates = raw.index[position:][raw[asset].iloc[position:].isna()]
                prices.loc[missing_dates, asset] = liquidation_price
                safe = next((candidate for candidate in NDX_SAFE if candidate in prior_targets), "BIL")
                prior_targets.pop(asset, None)
                prior_targets[safe] = prior_targets.get(safe, 0.0) + weight
                events.loc[date] = 0.0
                for holding, target in prior_targets.items():
                    events.at[date, holding] = target
    return events.dropna(how="all"), prices


def haa_monthly_targets(prices: pd.DataFrame, *, top_k: int) -> pd.DataFrame:
    """HAA G8 with TIP canary and 13612U momentum; K=1 or K=4."""
    required = (*HAA_OFFENSIVE, *HAA_SAFE, "TIP")
    missing = sorted(set(required) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing HAA price columns: {', '.join(missing)}")
    if top_k not in (1, 4):
        raise ValueError("HAA top_k must be 1 (Simple) or 4 (Balanced).")

    monthly = _month_ends(prices.sort_index())
    history: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for signal_date in monthly.index:
        available_history = monthly.loc[:signal_date]
        if len(available_history) < 13:
            continue
        safe = _best_safe(available_history, HAA_SAFE)
        tip_score = _momentum(available_history, "TIP")
        if not np.isfinite(tip_score) or tip_score <= 0:
            history.append((signal_date, {safe: 1.0}))
            continue

        scores = {ticker: _momentum(available_history, ticker) for ticker in HAA_OFFENSIVE}
        scores = {ticker: score for ticker, score in scores.items() if np.isfinite(score)}
        ranked = sorted(scores, key=scores.get, reverse=True)[:top_k]
        if not ranked:
            history.append((signal_date, {safe: 1.0}))
            continue
        weights: dict[str, float] = {}
        slot = 1.0 / top_k
        for ticker in ranked:
            if scores[ticker] > 0:
                weights[ticker] = weights.get(ticker, 0.0) + slot
            else:
                weights[safe] = weights.get(safe, 0.0) + slot
        if len(ranked) < top_k:
            weights[safe] = weights.get(safe, 0.0) + slot * (top_k - len(ranked))
        history.append((signal_date, weights))
    return _events_from_signals(prices, history)


def haa_simple_targets(prices: pd.DataFrame) -> pd.DataFrame:
    """HAA-Simple: TIP canary, then SPY trend; otherwise best of BIL/IEF."""
    required = ("SPY", "TIP", *HAA_SAFE)
    missing = sorted(set(required) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing HAA-Simple price columns: {', '.join(missing)}")

    monthly = _month_ends(prices.sort_index())
    history: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for signal_date in monthly.index:
        available_history = monthly.loc[:signal_date]
        if len(available_history) < 13:
            continue
        tip_score = _momentum(available_history, "TIP")
        spy_score = _momentum(available_history, "SPY")
        if tip_score > 0 and spy_score > 0:
            weights = {"SPY": 1.0}
        else:
            weights = {_best_safe(available_history, HAA_SAFE): 1.0}
        history.append((signal_date, weights))
    return _events_from_signals(prices, history)


def haa_balanced_targets(prices: pd.DataFrame) -> pd.DataFrame:
    return haa_monthly_targets(prices, top_k=4)


def aaa_monthly_targets(prices: pd.DataFrame) -> pd.DataFrame:
    """Canonical AAA: top five by six-month return, min-var weighted covariance."""
    required = AAA_UNIVERSE
    missing = sorted(set(required) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing AAA price columns: {', '.join(missing)}")

    prices = prices.sort_index()
    monthly = _month_ends(prices)
    daily_returns = prices.loc[:, AAA_UNIVERSE].pct_change(fill_method=None)
    history: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for signal_date in monthly.index:
        daily_history = prices.loc[:signal_date, AAA_UNIVERSE]
        if len(daily_history) < 127:
            continue
        scores = daily_history.iloc[-1] / daily_history.iloc[-127] - 1.0
        selected = list(scores.sort_values(ascending=False).index[:5])

        corr_returns = daily_returns.loc[:signal_date, selected].tail(126)
        vol_returns = daily_returns.loc[:signal_date, selected].tail(20)
        correlation = corr_returns.corr().to_numpy(dtype=float)
        volatility = vol_returns.std(ddof=1).to_numpy(dtype=float)
        covariance = correlation * np.outer(volatility, volatility)
        n_assets = len(selected)
        constraints = ({"type": "eq", "fun": lambda weights: weights.sum() - 1.0},)
        result = minimize(
            lambda weights: float(weights @ covariance @ weights),
            np.full(n_assets, 1.0 / n_assets), method="SLSQP",
            bounds=[(0.0, 1.0)] * n_assets, constraints=constraints,
        )
        weights = result.x if result.success else np.full(n_assets, 1.0 / n_assets)
        weights = np.clip(weights, 0.0, 1.0)
        weights /= weights.sum()
        history.append((signal_date, {ticker: float(weights[i]) for i, ticker in enumerate(selected)}))
    return _events_from_signals(prices, history)


def baa_g12_targets(prices: pd.DataFrame) -> pd.DataFrame:
    """BAA-G12/T6: four 13612W canaries; SMA12-ranked offensive/defensive sleeves."""
    required = (*BAA_CANARIES, *BAA_OFFENSIVE, *BAA_DEFENSIVE)
    missing = sorted(set(required) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing BAA price columns: {', '.join(missing)}")

    monthly = _month_ends(prices.sort_index())
    history: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for signal_date in monthly.index:
        available_history = monthly.loc[:signal_date]
        if len(available_history) < 13:
            continue
        canary_scores = [_momentum(available_history, ticker, weighted=True) for ticker in BAA_CANARIES]
        offensive = all(np.isfinite(score) and score > 0 for score in canary_scores)
        if offensive:
            scores = {ticker: _sma12_relative(available_history, ticker) for ticker in BAA_OFFENSIVE}
            valid = {ticker: score for ticker, score in scores.items() if np.isfinite(score)}
            selected = sorted(valid, key=valid.get, reverse=True)[:6]
            weights = {ticker: 1.0 / len(selected) for ticker in selected} if selected else {"BIL": 1.0}
        else:
            scores = {ticker: _sma12_relative(available_history, ticker) for ticker in BAA_DEFENSIVE}
            valid = {ticker: score for ticker, score in scores.items() if np.isfinite(score)}
            if not valid:
                weights = {"BIL": 1.0}
            else:
                bill_score = valid.get("BIL", -np.inf)
                selected = sorted(valid, key=valid.get, reverse=True)[:3]
                weights = {}
                for ticker in selected:
                    holding = "BIL" if valid[ticker] < bill_score else ticker
                    weights[holding] = weights.get(holding, 0.0) + 1.0 / 3.0
                if len(selected) < 3:
                    weights["BIL"] = weights.get("BIL", 0.0) + (3 - len(selected)) / 3.0
        history.append((signal_date, weights))
    return _events_from_signals(prices, history)


def vaa_g12_targets(prices: pd.DataFrame) -> pd.DataFrame:
    """VAA-G12: 13612W breadth defense, top-two offensive and top bond sleeves."""
    required = (*VAA_G12_OFFENSIVE, *VAA_G12_DEFENSIVE)
    missing = sorted(set(required) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing VAA-G12 price columns: {', '.join(missing)}")

    monthly = _month_ends(prices.sort_index())
    history: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for signal_date in monthly.index:
        available_history = monthly.loc[:signal_date]
        if len(available_history) < 13:
            continue

        offensive_scores = {
            ticker: _momentum(available_history, ticker, weighted=True)
            for ticker in VAA_G12_OFFENSIVE
        }
        defensive_scores = {
            ticker: _momentum(available_history, ticker, weighted=True)
            for ticker in VAA_G12_DEFENSIVE
        }
        valid_offensive = {ticker: score for ticker, score in offensive_scores.items() if np.isfinite(score)}
        valid_defensive = {ticker: score for ticker, score in defensive_scores.items() if np.isfinite(score)}
        if len(valid_offensive) != len(VAA_G12_OFFENSIVE) or not valid_defensive:
            continue

        breadth = sum(score <= 0 for score in valid_offensive.values())
        defensive_pick = max(valid_defensive, key=valid_defensive.get)
        ranked = sorted(valid_offensive, key=valid_offensive.get, reverse=True)
        if breadth >= 4:
            weights = {defensive_pick: 1.0}
        elif breadth >= 2:
            weights = {ranked[0]: 0.5, defensive_pick: 0.5}
        else:
            weights = {ranked[0]: 0.5, ranked[1]: 0.5}
        history.append((signal_date, weights))
    return _events_from_signals(prices, history)
