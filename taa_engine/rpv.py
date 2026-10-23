from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from .strategies import _events_from_signals


WINDOW_MONTHS = 120
BURN_IN = 36
EARNINGS_LAG_MONTHS = 4
ASSET_OF = {
    "term": "TLT",
    "igcredit": "LQD",
    "equity": "SPY",
    "hycredit": "HYG",
    "realyld": "TIP",
}
RPV_ASSETS = tuple(ASSET_OF.values()) + ("BIL",)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "rpv_macro"
CACHE_DIR = Path(".cache/rpv_macro")
FRED_SERIES = ("DGS10", "DGS3MO", "DBAA", "SP500", "BAA", "DAAA")


def _parse_date_value(frame: pd.DataFrame, name: str) -> pd.Series:
    if frame.shape[1] < 2:
        raise ValueError(f"Expected date and value columns for {name}.")
    out = frame.iloc[:, :2].copy()
    out.columns = ["date", name]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out[name] = pd.to_numeric(out[name], errors="coerce")
    out = out.dropna(subset=["date", name]).set_index("date").sort_index()
    return out[name]


def _fetch_csv(url: str) -> pd.DataFrame:
    with urlopen(url, timeout=20) as response:
        return pd.read_csv(response)


def _fred_series(series_id: str, *, refresh: bool) -> tuple[pd.Series, str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_path = CACHE_DIR / f"fred_{series_id}.csv"
    fallback_path = DATA_DIR / f"fred_{series_id}.csv"
    source = "cache" if cached_path.exists() else "bundled snapshot"
    if refresh:
        try:
            remote = _fetch_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
            if remote.shape[1] < 2:
                raise ValueError(f"FRED returned an invalid {series_id} CSV.")
            remote.to_csv(cached_path, index=False)
            source = "FRED refreshed"
        except Exception:
            source += " (FRED refresh unavailable)"
    path = cached_path if cached_path.exists() else fallback_path
    if not path.exists():
        raise FileNotFoundError(f"Missing macro series {series_id}: expected {path}.")
    return _parse_date_value(pd.read_csv(path), series_id), source


def _cpi_first_release(*, refresh: bool) -> tuple[pd.Series, str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_path = CACHE_DIR / "fred_realtime_CPIAUCSL.csv"
    fallback_path = DATA_DIR / "fred_realtime_CPIAUCSL.csv"
    source = "cache" if cached_path.exists() else "bundled ALFRED snapshot"
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if refresh and api_key:
        try:
            params = urlencode({
                "series_id": "CPIAUCSL", "realtime_start": "1776-07-04",
                "realtime_end": "9999-12-31", "api_key": api_key, "file_type": "json",
            })
            with urlopen(f"https://api.stlouisfed.org/fred/series/observations?{params}", timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            observations = payload.get("observations")
            if not isinstance(observations, list) or not observations:
                raise ValueError("FRED returned no CPI vintage observations.")
            data = pd.DataFrame(observations)
            data["date"] = pd.to_datetime(data["date"])
            data["realtime_start"] = pd.to_datetime(data["realtime_start"])
            data["value"] = pd.to_numeric(data["value"], errors="coerce")
            data = data.dropna(subset=["value"]).sort_values("realtime_start").groupby("date", as_index=False).first()
            data[["date", "value"]].to_csv(cached_path, index=False)
            source = "ALFRED first releases refreshed"
        except Exception:
            source += " (ALFRED refresh unavailable)"
    elif refresh:
        source += " (no FRED_API_KEY; using cached first releases)"
    path = cached_path if cached_path.exists() else fallback_path
    if not path.exists():
        raise FileNotFoundError("Missing CPI first-release data; provide FRED_API_KEY or a bundled ALFRED snapshot.")
    return _parse_date_value(pd.read_csv(path), "CPIAUCSL"), source


def _shiller_earnings(*, refresh: bool) -> tuple[pd.Series, pd.Series, str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_path = CACHE_DIR / "sp500_earnings.csv"
    fallback_path = DATA_DIR / "sp500_earnings.csv"
    source = "cache" if cached_path.exists() else "bundled Shiller snapshot"
    if refresh:
        try:
            remote = _fetch_csv("https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv")
            remote.to_csv(cached_path, index=False)
            source = "Shiller dataset refreshed"
        except Exception:
            source += " (refresh unavailable)"
    path = cached_path if cached_path.exists() else fallback_path
    if not path.exists():
        raise FileNotFoundError("Missing S&P 500 earnings history.")
    data = pd.read_csv(path)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"]).set_index("Date").sort_index()
    earnings = pd.to_numeric(data["Earnings"], errors="coerce")
    earnings = earnings.where(earnings > 0).ffill().dropna()
    price = pd.to_numeric(data["SP500"], errors="coerce").dropna()
    return earnings, price, source


def _rolling_zscores(premia: pd.DataFrame) -> pd.DataFrame:
    return premia.apply(lambda column: (
        (column - column.rolling(WINDOW_MONTHS).mean())
        / column.rolling(WINDOW_MONTHS).std(ddof=0)
    ))


def load_rpv_signals(prices: pd.DataFrame, *, refresh: bool = True) -> tuple[pd.DataFrame, str]:
    """Build the old RPV 5-premia z-score panel using lagged first-release CPI."""
    loaded = {series_id: _fred_series(series_id, refresh=refresh) for series_id in FRED_SERIES}
    cpi, cpi_status = _cpi_first_release(refresh=refresh)
    earnings, shiller_price, earnings_status = _shiller_earnings(refresh=refresh)
    monthly = lambda series: series.resample("ME").last()

    dgs10, dgs10_status = loaded["DGS10"]
    dgs3mo, dgs3mo_status = loaded["DGS3MO"]
    dbaa, dbaa_status = loaded["DBAA"]
    baa, baa_status = loaded["BAA"]
    daaa, daaa_status = loaded["DAAA"]
    sp500, sp500_status = loaded["SP500"]
    dgs10_m, dgs3mo_m = monthly(dgs10), monthly(dgs3mo)
    dbaa_m, baa_m, daaa_m = monthly(dbaa), monthly(baa), monthly(daaa)
    sp500_m = monthly(sp500)

    earnings_m = monthly(earnings)
    earnings_m = earnings_m.reindex(pd.date_range(
        earnings_m.index.min(), max(pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(0), earnings_m.index.max()), freq="ME",
    )).ffill()
    shiller_price_m = monthly(shiller_price)
    price_m = shiller_price_m.copy()
    fred_overlap = price_m.index.intersection(sp500_m.index)
    if len(fred_overlap):
        fred_scale = float(price_m.loc[fred_overlap[-1]] / sp500_m.loc[fred_overlap[-1]])
        fred_extension = sp500_m.loc[sp500_m.index > price_m.index.max()] * fred_scale
        price_m = pd.concat([price_m, fred_extension]).sort_index().ffill()
    spy_m = prices["SPY"].resample("ME").last().dropna()
    spy_overlap = price_m.index.intersection(spy_m.index)
    if len(spy_overlap):
        spy_scale = float(price_m.loc[spy_overlap[-1]] / spy_m.loc[spy_overlap[-1]])
        spy_extension = spy_m.loc[spy_m.index > price_m.index.max()] * spy_scale
        price_m = pd.concat([price_m, spy_extension]).sort_index().ffill()
    ey = (100.0 * (earnings_m.shift(EARNINGS_LAG_MONTHS) / price_m)).dropna()

    cpi_m = monthly(cpi)
    cpi_yoy = 100.0 * (cpi_m / cpi_m.shift(12) - 1.0)
    cpi_yoy_known = cpi_yoy.shift(1).reindex(dgs10_m.index).ffill()
    premia = pd.DataFrame({
        "term": dgs10_m - dgs3mo_m,
        "igcredit": dbaa_m - dgs10_m,
        "equity": ey - dgs10_m,
        "hycredit": baa_m - daaa_m,
        "realyld": dgs10_m - cpi_yoy_known,
    }).sort_index()
    zscores = _rolling_zscores(premia).dropna(how="all")
    ready = zscores.dropna()
    if len(ready) > BURN_IN:
        zscores = zscores.loc[zscores.index >= ready.index[BURN_IN]]
    statuses = (dgs10_status, dgs3mo_status, dbaa_status, baa_status, daaa_status, sp500_status, cpi_status, earnings_status)
    return zscores, "; ".join(dict.fromkeys(statuses))


def rpv_monthly_targets(prices: pd.DataFrame, zscores: pd.DataFrame) -> pd.DataFrame:
    """Old sequential positive-premium/SMA200 gate and z-strength weighting."""
    missing = sorted(set(RPV_ASSETS) - set(prices.columns))
    if missing:
        raise ValueError(f"Missing RPV price columns: {', '.join(missing)}")
    monthly_prices = prices.groupby(prices.index.to_period("M")).tail(1)
    signal_periods = {period: row for period, row in zip(zscores.index.to_period("M"), zscores.itertuples(index=False, name=None))}
    history: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for date in monthly_prices.index:
        row_values = signal_periods.get(date.to_period("M"))
        if row_values is None:
            prior = zscores.loc[zscores.index.to_period("M") <= date.to_period("M")]
            if prior.empty:
                continue
            row = prior.iloc[-1]
        else:
            row = pd.Series(row_values, index=zscores.columns)
        survivors: list[tuple[str, float]] = []
        for premium, score in row.dropna().items():
            asset = ASSET_OF[premium]
            series = prices[asset].ffill().loc[:date]
            if score > 0 and len(series) >= 200:
                average = series.rolling(200).mean().iloc[-1]
                if pd.notna(average) and series.iloc[-1] > average:
                    survivors.append((asset, float(score)))
        if not survivors:
            weights = {"BIL": 1.0}
        else:
            strength_total = sum(strength for _, strength in survivors)
            weights = {}
            if strength_total <= 0:
                weights = {"BIL": 1.0}
            else:
                for asset, strength in survivors:
                    raw_weight = strength / strength_total
                    weights[asset] = weights.get(asset, 0.0) + min(1.0, raw_weight)
                invested = sum(weights.values())
                if invested < 1.0:
                    weights["BIL"] = weights.get("BIL", 0.0) + 1.0 - invested
        history.append((date, weights))
    return _events_from_signals(prices, history)
