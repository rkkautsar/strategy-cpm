from __future__ import annotations

import argparse
from pathlib import Path
import os

import pandas as pd
from dotenv import load_dotenv

from .backtest import build_portfolios, equity_curves, summarize
from .cpm import cpm_monthly_targets
from .dashboard import build_dashboard
from .data import load_daily_prices, load_ndx_constituent_prices
from .rpv import load_rpv_signals, rpv_monthly_targets
from .value import load_valuein_cache, val_monthly_targets
from .strategies import (
    aaa_monthly_targets, baa_g12_targets, haa_balanced_targets, haa_simple_targets,
    ndx_backtest_inputs, ndx_monthly_targets, vaa_g12_targets,
)


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(description="Compare monthly CPM, NDX, RPV, VAL, HAA, BAA, AAA, and VAA strategies.")
    parser.add_argument("--start", default="2007-01-01", help="First Yahoo Finance date (YYYY-MM-DD).")
    parser.add_argument("--end", default=None, help="Exclusive Yahoo Finance end date (YYYY-MM-DD).")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Transaction cost per side in basis points.")
    parser.add_argument("--cash", type=float, default=100_000.0, help="Initial portfolio value.")
    parser.add_argument("--output", type=Path, default=Path("results"), help="Directory for CSV outputs.")
    parser.add_argument("--refresh", action="store_true", help="Redownload and replace the full local price cache.")
    parser.add_argument("--no-refresh-macro", action="store_true", help="Use cached/bundled RPV macro data without refreshing public sources.")
    parser.add_argument("--valuein-cache", type=Path, default=Path(os.environ.get("VALUEIN_CACHE_DIR", ".cache/valuein")), help="Directory containing local Valuein parquet snapshots.")
    args = parser.parse_args()

    prices, data_status = load_daily_prices(
        start=args.start, end=args.end, refresh=args.refresh,
    )
    ndx_prices, ndx_data_status = load_ndx_constituent_prices(
        start=args.start, end=args.end, refresh=args.refresh,
    )
    rpv_signals, rpv_data_status = load_rpv_signals(
        prices, refresh=not args.no_refresh_macro or args.refresh,
    )
    val_flows, val_balance_sheets, val_data_status = load_valuein_cache(args.valuein_cache)
    targets = cpm_monthly_targets(prices)
    additional_targets = {
        "HAA-Simple": haa_simple_targets(prices),
        "HAA-Balanced": haa_balanced_targets(prices),
        "BAA-G12": baa_g12_targets(prices),
        "AAA": aaa_monthly_targets(prices),
        "VAA-G12": vaa_g12_targets(prices),
        "NDX": ndx_monthly_targets(prices, ndx_prices),
        "RPV": rpv_monthly_targets(prices, rpv_signals),
        "VAL": val_monthly_targets(prices, ndx_prices, val_flows, val_balance_sheets),
    }
    additional_targets["NDX"], ndx_backtest_prices = ndx_backtest_inputs(
        prices, ndx_prices, additional_targets["NDX"],
    )
    additional_targets["VAL"], val_backtest_prices = ndx_backtest_inputs(
        prices, ndx_prices, additional_targets["VAL"],
    )
    fee_rate = args.fee_bps / 10_000.0
    portfolios, targets = build_portfolios(
        prices, targets, initial_cash=args.cash, fee_rate=fee_rate,
        additional_targets=additional_targets,
        additional_prices={"NDX": ndx_backtest_prices, "VAL": val_backtest_prices},
    )
    metrics = summarize(portfolios, initial_cash=args.cash)

    args.output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.output / "performance.csv")
    equity_curves(portfolios).to_csv(args.output / "equity.csv", index_label="date")
    targets.to_csv(args.output / "target_weights.csv", index_label="date")
    pd.concat(additional_targets, axis=1).to_csv(args.output / "comparison_targets.csv", index_label="date")
    dashboard_path = build_dashboard(
        prices=prices,
        strategy_targets={"CPM": targets, **additional_targets},
        portfolios=portfolios,
        metrics=metrics,
        output_path=args.output / "dashboard.html",
        fee_bps=args.fee_bps,
        rebalance_dates=sorted({
            date
            for events in (targets, *additional_targets.values())
            for date in events.dropna(how="all").index
        }),
    )

    print(f"Data: {prices.index[0].date()} to {prices.index[-1].date()} ({len(prices):,} daily rows)")
    print(f"Prices: {data_status}")
    print(f"NDX data: {ndx_data_status}")
    print(f"RPV macro data: {rpv_data_status}")
    print(f"VAL fundamentals: {val_data_status}")
    print(f"Fee: {args.fee_bps:g} bps per side | Execution: next trading day close")
    display_metrics = metrics.copy()
    for column in ("Total return", "CAGR", "Volatility", "Max drawdown"):
        display_metrics[column] = display_metrics[column].map(lambda value: f"{value:.2%}")
    display_metrics["Sharpe"] = display_metrics["Sharpe"].map(lambda value: f"{value:.2f}")
    print(display_metrics.to_string())
    print(f"Saved outputs to {args.output.resolve()}")
    print(f"Dashboard: {dashboard_path.resolve()}")


if __name__ == "__main__":
    main()
