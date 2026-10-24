from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_ENABLED_STRATEGIES = (
    "CPM", "HAA-Simple", "HAA-Balanced", "NDX", "RPV", "VAL",
)


def build_dashboard(
    *,
    prices: pd.DataFrame,
    strategy_targets: dict[str, pd.DataFrame],
    portfolios: dict,
    metrics: pd.DataFrame,
    output_path: Path,
    fee_bps: float,
    rebalance_dates: list[pd.Timestamp],
    strategy_notes: dict[str, str] | None = None,
) -> Path:
    """Write a mobile-friendly static dashboard without publishing price bars."""
    as_of = prices.index[-1]
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    portfolio_values = {}
    colors = {
        "CPM": "#147d8b", "HAA-Simple": "#8b67b4", "HAA-Balanced": "#3399cc",
        "BAA-G12": "#c28725", "AAA": "#778397", "VAA-G12": "#cb5973", "NDX": "#d45b42", "RPV": "#34875b", "VAL": "#bd6e35", "SPY B&H": "#a6afbd",
        "60/40 Annual": "#5476d2",
    }
    for name, portfolio in portfolios.items():
        value = portfolio.value() if hasattr(portfolio, "value") else portfolio
        if isinstance(value, pd.DataFrame):
            value = value.iloc[:, 0]
        portfolio_values[str(name)] = value.dropna()

    # Anchor the shared view to strategies enabled by default in the selector.
    # Optional strategies remain available, but should not shorten the default
    # comparison window until a user enables them.
    enabled_values = {
        name: portfolio_values[name]
        for name in DEFAULT_ENABLED_STRATEGIES
        if name in portfolio_values and not portfolio_values[name].empty
    }
    if not enabled_values:
        raise ValueError("No enabled strategy portfolios are available for the dashboard.")
    common_start = max(value.index[0] for value in enabled_values.values())
    common_end = min(value.index[-1] for value in enabled_values.values())
    portfolio_values = {
        name: value.loc[(value.index >= common_start) & (value.index <= common_end)]
        for name, value in portfolio_values.items()
    }

    chart_data = []
    for name, value in portfolio_values.items():
        chart_data.append({
            "name": str(name),
            "color": colors.get(str(name), "#7a8797"),
            "dates": [timestamp.strftime("%Y-%m-%d") for timestamp in value.index],
            "values": [float(item) for item in value.to_numpy()],
        })
    blendable_names = [name for name in ("CPM", "HAA-Simple", "HAA-Balanced", "BAA-G12", "AAA", "VAA-G12", "NDX", "RPV", "VAL") if name in portfolios]
    blend_controls = "".join(
        f'<label class="blend-leg"><input type="checkbox" class="blend-enabled" data-strategy="{escape(name)}">'
        f'<span>{escape(name)}</span><input type="number" class="blend-weight" data-strategy="{escape(name)}" '
        f'min="0" max="100" step="5" value="0" disabled aria-label="{escape(name)} target percent">'
        f'<span>%</span></label>'
        for name in blendable_names
    )
    rebalance_date_values = [pd.Timestamp(date).strftime("%Y-%m-%d") for date in rebalance_dates]
    blend_target_state = {}
    for name in blendable_names:
        events = strategy_targets[name].dropna(how="all")
        if events.empty:
            continue
        current_targets = events.iloc[-1].fillna(0.0)
        previous_targets = events.iloc[-2].fillna(0.0) if len(events) > 1 else pd.Series(0.0, index=events.columns)
        blend_target_state[name] = {
            "current_date": events.index[-1].strftime("%Y-%m-%d"),
            "previous_date": events.index[-2].strftime("%Y-%m-%d") if len(events) > 1 else None,
            "current": {str(ticker): float(weight) for ticker, weight in current_targets.items() if abs(float(weight)) > 1e-8},
            "previous": {str(ticker): float(weight) for ticker, weight in previous_targets.items() if abs(float(weight)) > 1e-8},
        }
    notification_data = {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "targets": blend_target_state,
        "notes": strategy_notes or {},
    }
    strategy_descriptions = {
        "CPM": "Ranks risky assets by trend-adjusted momentum and scales risk with market breadth.",
        "HAA-Simple": "Uses the SPY trend signal with a TIP canary and BIL as the defensive asset.",
        "HAA-Balanced": "Ranks a diversified ETF universe by momentum with a defensive sleeve.",
        "BAA-G12": "Uses 1/3/6/12-month momentum and a canary to control defensive shifts.",
        "AAA": "Selects the five strongest assets and assigns minimum-variance weights.",
        "VAA-G12": "Rotates among global assets and defensive bonds using 1/3/6/12-month momentum.",
        "NDX": "Applies a momentum rotation to point-in-time Nasdaq-100 constituents.",
        "RPV": "Allocates across asset classes using rolling valuation and risk-premia signals.",
        "VAL": "Ranks Valuein-covered Nasdaq-100 companies using point-in-time value and quality fundamentals.",
    }

    def performance_row(name: str, value: pd.Series, cutoff: pd.Timestamp | None = None) -> dict:
        period = value.loc[value.index >= cutoff] if cutoff is not None else value
        daily_returns = period.pct_change().dropna()
        elapsed_years = max((period.index[-1] - period.index[0]).days / 365.25, 1 / 365.25)
        total_return = float(period.iloc[-1] / period.iloc[0] - 1)
        daily_volatility = daily_returns.std(ddof=1) if len(daily_returns) > 1 else 0.0
        return {
            "name": name,
            "total_return": total_return,
            "cagr": float((period.iloc[-1] / period.iloc[0]) ** (1 / elapsed_years) - 1),
            "volatility": float(daily_volatility * np.sqrt(252)),
            "sharpe": float(daily_returns.mean() / daily_volatility * np.sqrt(252))
            if daily_volatility > 0 else 0.0,
            "max_drawdown": float((period / period.cummax() - 1).min()),
        }

    performance_data = {
        "all": [performance_row(name, value) for name, value in portfolio_values.items()]
    }
    end_date = common_end
    for years in (10, 5, 3, 1):
        cutoff = end_date - pd.DateOffset(years=years)
        rows = []
        for name, value in portfolio_values.items():
            period = value.loc[value.index >= cutoff]
            if len(period) < 2:
                continue
            rows.append(performance_row(name, value, cutoff))
        performance_data[str(years)] = rows
    dashboard_data = {
        "portfolios": chart_data,
        "performance": performance_data,
        "targets": blend_target_state,
        "strategies": blendable_names,
        "descriptions": {name: strategy_descriptions[name] for name in blendable_names},
        "rebalance_dates": rebalance_date_values,
        "comparison_start": common_start.strftime("%Y-%m-%d"),
        "comparison_end": common_end.strftime("%Y-%m-%d"),
    }
    dashboard_data_json = json.dumps(dashboard_data, separators=(",", ":"))
    asset_name = f"dashboard-data-{sha256(dashboard_data_json.encode('utf-8')).hexdigest()[:16]}.json"

    template_path = Path(__file__).resolve().parent / "templates" / "dashboard.html"
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    environment = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(("html", "xml")),
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = environment.get_template(template_path.name).render(
        as_of=escape(as_of.strftime("%d %b %Y")),
        built_at=escape(built_at),
        data_asset_url=escape(asset_name),
        blend_controls=blend_controls,
        period=escape(f"{common_start:%d %b %Y} – {common_end:%d %b %Y}"),
        fee_bps=f"{fee_bps:g}",
    )

    for previous_asset in output_path.parent.glob("dashboard-data-*.json"):
        if previous_asset.name != asset_name:
            previous_asset.unlink()
    (output_path.parent / asset_name).write_text(dashboard_data_json, encoding="utf-8")
    output_path.write_text(html, encoding="utf-8")
    output_path.with_name("notification_data.json").write_text(
        json.dumps(notification_data, separators=(",", ":")), encoding="utf-8"
    )
    return output_path
