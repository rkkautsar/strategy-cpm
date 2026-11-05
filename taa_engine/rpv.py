from __future__ import annotations

import json
import os
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import io

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


def _fetch_url(url: str, *, timeout: int) -> bytes:
    """Fetch a source response, retrying transient network and server errors."""
    for attempt in range(3):
        try:
            with urlopen(url, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429 and exc.code < 500:
                raise
            if attempt == 2:
                raise
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
        sleep(2 ** attempt)
    raise RuntimeError("Source request failed after retries.")


def _fetch_csv(url: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(_fetch_url(url, timeout=30)))


def _fred_series(series_id: str) -> tuple[pd.Series, str]:
    """Fetch the full current series; never read or persist a local snapshot."""
    query = urlencode({"id": series_id})
    try:
        remote = _fetch_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}")
        if remote.shape[1] < 2:
            raise ValueError("FRED returned a CSV without date and value columns.")
        return _parse_date_value(remote, series_id), "FRED full history fetched fresh"
    except Exception as exc:
        raise RuntimeError(f"Fresh FRED fetch failed for {series_id}.") from exc


def _cpi_first_release() -> tuple[pd.Series, str]:
    """Fetch ALFRED's first-release CPI observations without writing a cache."""
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Fresh ALFRED CPI fetch requires FRED_API_KEY.")
    params = {
        "series_id": "CPIAUCSL", "api_key": api_key, "file_type": "json",
        # ALFRED otherwise defaults the real-time period to today. On dates
        # without a vintage (for example weekends), that returns HTTP 400.
        # Initial-release output needs the full vintage span to return history.
        "output_type": 4, "limit": 100000,
        "realtime_start": "1776-07-04", "realtime_end": "9999-12-31",
    }
    observations: list[dict] = []
    offset = 0
    expected_count: int | None = None
    try:
        while expected_count is None or offset < expected_count:
            params["offset"] = offset
            url = f"https://api.stlouisfed.org/fred/series/observations?{urlencode(params)}"
            payload = json.loads(_fetch_url(url, timeout=30).decode("utf-8"))
            batch = payload.get("observations")
            if not isinstance(batch, list) or not batch:
                raise ValueError("FRED returned an incomplete CPI first-release history.")
            expected_count = int(payload.get("count", len(batch)))
            observations.extend(batch)
            offset += len(batch)
        if len(observations) != expected_count:
            raise ValueError(f"FRED returned {len(observations)} of {expected_count} CPI observations.")
        data = pd.DataFrame(observations)
        return _parse_date_value(data[["date", "value"]], "CPIAUCSL"), "ALFRED full first-release history fetched fresh"
    except Exception as exc:
        raise RuntimeError("Fresh ALFRED first-release CPI fetch failed.") from exc


def _shiller_earnings() -> tuple[pd.Series, pd.Series, str]:
    """Fetch the complete Shiller-derived history without keeping a local copy."""
    try:
        data = _fetch_csv("https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv")
    except Exception as exc:
        raise RuntimeError("Fresh Shiller earnings source fetch failed.") from exc
    if not {"Date", "Earnings", "SP500"}.issubset(data.columns):
        raise ValueError("Shiller source CSV is missing Date, Earnings, or SP500 columns.")
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"]).set_index("Date").sort_index()
    earnings = pd.to_numeric(data["Earnings"], errors="coerce")
    earnings = earnings.where(earnings > 0).ffill().dropna()
    price = pd.to_numeric(data["SP500"], errors="coerce").dropna()
    return earnings, price, "Shiller history fetched fresh"


def _rolling_zscores(premia: pd.DataFrame) -> pd.DataFrame:
    return premia.apply(lambda column: (
        (column - column.rolling(WINDOW_MONTHS).mean())
        / column.rolling(WINDOW_MONTHS).std(ddof=0)
    ))


def load_rpv_signals(prices: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Build the old RPV 5-premia z-score panel using lagged first-release CPI."""
    loaded = {series_id: _fred_series(series_id) for series_id in FRED_SERIES}
    cpi, cpi_status = _cpi_first_release()
    earnings, shiller_price, earnings_status = _shiller_earnings()
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


def rpv_monthly_targets(
    prices: pd.DataFrame,
    zscores: pd.DataFrame,
    *,
    pending_execution_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
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
    return _events_from_signals(prices, history, pending_execution_date=pending_execution_date)
