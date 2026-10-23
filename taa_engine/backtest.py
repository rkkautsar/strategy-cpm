from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt


def build_portfolios(
    prices: pd.DataFrame, target_events: pd.DataFrame, *,
    initial_cash: float = 100_000.0, fee_rate: float = 0.001,
    additional_targets: dict[str, pd.DataFrame] | None = None,
    additional_prices: dict[str, pd.DataFrame] | None = None,
) -> tuple[dict[str, vbt.Portfolio | pd.Series], pd.DataFrame]:
    """Simulate CPM, added monthly strategies, SPY, and static 60/40."""
    if target_events.empty:
        raise ValueError("No CPM target weights were generated for this date range.")

    full_prices = prices

    def simulate_target_events(events: pd.DataFrame, price_panel: pd.DataFrame = full_prices) -> vbt.Portfolio:
        first_date = events.dropna(how="all").index[0]
        close = price_panel.loc[first_date:]
        targets = events.reindex(close.index).reindex(columns=close.columns)
        return vbt.Portfolio.from_orders(
            close=close,
            size=targets,
            size_type="targetpercent",
            price=close,
            fees=fee_rate,
            init_cash=initial_cash,
            cash_sharing=True,
            group_by=True,
            call_seq="auto",
            freq="1D",
        )

    cpm = simulate_target_events(target_events)
    benchmark_start = target_events.dropna(how="all").index[0]
    prices = full_prices.loc[benchmark_start:]

    portfolios: dict[str, vbt.Portfolio | pd.Series] = {"CPM": cpm}
    stock_growth = prices["SPY"] / prices["SPY"].iloc[0]
    # SPY buy-and-hold pays only the initial purchase fee.
    portfolios["SPY B&H"] = initial_cash * (1.0 - fee_rate) * stock_growth
    balanced_targets = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    rebalance_positions = [0]
    years = prices.index.year
    rebalance_positions.extend(i for i in range(1, len(prices.index)) if years[i] != years[i - 1])
    for position in rebalance_positions:
        balanced_targets.iloc[position] = 0.0
        balanced_targets.iat[position, prices.columns.get_loc("SPY")] = 0.6
        balanced_targets.iat[position, prices.columns.get_loc("AGG")] = 0.4
    portfolios["60/40 Annual"] = simulate_target_events(balanced_targets)
    for name, events in (additional_targets or {}).items():
        if events.dropna(how="all").empty:
            continue
        portfolios[name] = simulate_target_events(events, (additional_prices or {}).get(name, full_prices))
    return portfolios, target_events


def summarize(portfolios: dict[str, vbt.Portfolio | pd.Series], *, initial_cash: float) -> pd.DataFrame:
    """Small transparent set of net performance statistics."""
    rows = {}
    for name, portfolio in portfolios.items():
        value = portfolio.value() if hasattr(portfolio, "value") else portfolio
        if isinstance(value, pd.DataFrame):
            value = value.iloc[:, 0]
        value = value.dropna()
        daily_returns = value.pct_change().dropna()
        years = max((value.index[-1] - value.index[0]).days / 365.25, 1 / 365.25)
        total_return = float(value.iloc[-1] / initial_cash - 1.0)
        cagr = float((value.iloc[-1] / initial_cash) ** (1.0 / years) - 1.0)
        volatility = float(daily_returns.std(ddof=1) * np.sqrt(252)) if len(daily_returns) > 1 else 0.0
        sharpe = (
            float(daily_returns.mean() / daily_returns.std(ddof=1) * np.sqrt(252))
            if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0 else 0.0
        )
        drawdown = value / value.cummax() - 1.0
        rows[name] = {
            "Total return": total_return,
            "CAGR": cagr,
            "Volatility": volatility,
            "Sharpe": sharpe,
            "Max drawdown": float(drawdown.min()),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def equity_curves(portfolios: dict[str, vbt.Portfolio | pd.Series]) -> pd.DataFrame:
    curves = {}
    for name, portfolio in portfolios.items():
        value = portfolio.value() if hasattr(portfolio, "value") else portfolio
        if isinstance(value, pd.DataFrame):
            value = value.iloc[:, 0]
        curves[name] = value
    return pd.DataFrame(curves)
