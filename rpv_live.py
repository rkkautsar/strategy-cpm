#!/usr/bin/env python3
"""
RPV sleeve (Risk Premia Value).
Production implementation of the validated research variant:
seq/z/weighted/sma200 over a 5-premia universe + SHV cash.
"""
from __future__ import annotations

import io
import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

# Configuration
W = 120  # 120-month trailing window
ZMIN = 36
LAG_E = 4
COST_BPS_PER_SIDE = 10.0
CAP = 1.0

ASSET_OF = {
    "term": "TLT",
    "igcredit": "LQD",
    "equity": "SPY",
    "hycredit": "HYG",
    "realyld": "TIP",
}
RPV_RISKY_ASSETS = sorted(set(ASSET_OF.values()))
RPV_ASSETS = RPV_RISKY_ASSETS + ["SHV"]


def _read_csv_url_timeout(url: str, timeout_s: float = 15.0) -> pd.DataFrame:
    with urlopen(url, timeout=timeout_s) as response:
        text = response.read().decode("utf-8")
    return pd.read_csv(io.StringIO(text))


def _read_fred_api_observations_timeout(id_: str, api_key: str, timeout_s: float = 15.0) -> pd.DataFrame:
    params = urlencode({"series_id": id_, "api_key": api_key, "file_type": "json"})
    url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
    with urlopen(url, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))

    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(observations, list) or not observations:
        raise ValueError(f"Invalid FRED API payload for {id_}: missing observations")

    df_obs = pd.DataFrame(observations)
    if "date" not in df_obs.columns or "value" not in df_obs.columns:
        raise ValueError(f"Invalid FRED API payload for {id_}: missing date/value")

    return pd.DataFrame({"date": df_obs["date"], id_: df_obs["value"]})


def _parse_fred_series(df: pd.DataFrame, id_: str) -> pd.Series:
    if df.shape[1] < 2:
        raise ValueError(f"Invalid FRED payload for {id_}: expected >=2 columns")
    out = df.iloc[:, :2].copy()
    out.columns = ["date", id_]
    out["date"] = pd.to_datetime(out["date"])
    s = pd.to_numeric(out[id_], errors="coerce")
    s.index = out["date"]
    return s.dropna()


def _fetch_fred_series(id_: str, fallback_paths: list[Path] | None = None) -> pd.Series:
    """Fetch FRED series web-first ONLY if REFRESH_FRED=1 is set, otherwise read from committed fallback CSV(s)."""
    fallback_paths = fallback_paths or [DATA_DIR / f"fred_{id_}.csv"]

    if os.environ.get("REFRESH_FRED") == "1":
        api_key = os.environ.get("FRED_API_KEY", "").strip()
        try:
            if api_key:
                remote_df = _read_fred_api_observations_timeout(id_, api_key, timeout_s=15.0)
            else:
                url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
                remote_df = _read_csv_url_timeout(url, timeout_s=15.0)
            return _parse_fred_series(remote_df, id_)
        except Exception:
            pass

    for fpath in fallback_paths:
        if fpath.exists():
            return _parse_fred_series(pd.read_csv(fpath), id_)
    raise FileNotFoundError(f"FRED series {id_} not found locally and REFRESH_FRED not set or web fetch failed.")


from data_loader import load_macro_data


def _trailing_z(df: pd.DataFrame, w: int) -> pd.DataFrame:
    return df.apply(lambda s: (s - s.rolling(w).mean()) / s.rolling(w).std(ddof=0))


def _burn(sig: pd.DataFrame) -> pd.DataFrame:
    ready = sig.dropna()
    if len(ready) > ZMIN:
        return sig.loc[sig.index >= ready.index[ZMIN]]
    return sig


def _sma_above(prices: pd.DataFrame, asset: str, sig_d: pd.Timestamp, win: int = 200) -> bool:
    if asset not in prices.columns:
        return False
    s = prices[asset].sort_index().ffill().loc[:sig_d]
    if len(s) < win:
        return False
    sma = s.rolling(win).mean().iloc[-1]
    return bool(pd.notna(sma) and s.iloc[-1] > sma)


def _load_stitched_price(asset: str) -> pd.Series | None:
    stitched = {
        "HYG": (DATA_DIR / "hyg_stitched_daily.csv", "HYG"),
        "TIP": (DATA_DIR / "tip_stitched_daily.csv", "TIP_stitched"),
        "SHV": (DATA_DIR / "shv_stitched_daily.csv", "SHV"),
    }
    cfg = stitched.get(asset)
    if cfg is None:
        return None
    path, expected_col = cfg
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=[0], index_col=0)
    if df.empty:
        return None
    if expected_col in df.columns:
        s = df[expected_col]
    else:
        s = df.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.name = asset
    return s


def _build_rpv_price_panel(close_panel: pd.DataFrame) -> pd.DataFrame:
    cols: dict[str, pd.Series] = {}
    for asset in RPV_ASSETS:
        if asset in close_panel.columns:
            cols[asset] = pd.to_numeric(close_panel[asset], errors="coerce")
            continue
        stitched = _load_stitched_price(asset)
        if stitched is not None:
            cols[asset] = stitched
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index().ffill()


@lru_cache(maxsize=1)
def compute_rpv_signals() -> pd.DataFrame:
    """Compute trailing-120m z premia for term/igcredit/equity/hycredit/realyld."""
    dgs10, dgs3mo, dbaa, sp500, E, P = load_macro_data()

    me = lambda s: s.resample("ME").last()
    dgs10_m = me(dgs10)
    dgs3mo_m = me(dgs3mo)
    dbaa_m = me(dbaa)
    sp500_m = me(sp500)

    E_m = E.resample("ME").last()
    if not E_m.empty:
        ceiling = max(
            pd.Timestamp("2026-06-30"),
            pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(0),
            E_m.index.max(),
        )
        E_m = E_m.reindex(pd.date_range(E_m.index.min(), ceiling, freq="ME")).ffill()

    P_m = P.resample("ME").last()
    if not sp500_m.empty:
        ov = P_m.index.intersection(sp500_m.index)
        if len(ov) > 0:
            k = P_m.loc[ov[-1]] / sp500_m.loc[ov[-1]]
            P_m = pd.concat([P_m, sp500_m[sp500_m.index > P_m.index.max()] * k]).sort_index().ffill()

    ey = (100.0 * (E_m.shift(LAG_E) / P_m)).dropna()

    # hycredit proxy from Moody's Baa/Aaa pair.
    baa = _fetch_fred_series("BAA", fallback_paths=[DATA_DIR / "fred_BAA.csv"])
    daaa = _fetch_fred_series("DAAA", fallback_paths=[DATA_DIR / "fred_DAAA.csv", DATA_DIR / "fred_AAA.csv"])
    baa_m = me(baa)
    daaa_m = me(daaa)

    cpi = _fetch_fred_series("CPIAUCSL", fallback_paths=[DATA_DIR / "fred_CPIAUCSL.csv"])
    cpi_m = me(cpi)
    cpi_yoy = 100.0 * (cpi_m / cpi_m.shift(12) - 1.0)
    # Live-tail robustness without look-ahead: shift by 1 month to use last released (M-1) CPI at each signal month.
    cpi_yoy_last_known = cpi_yoy.shift(1).reindex(dgs10_m.index).ffill()

    rp = pd.DataFrame(
        {
            "term": (dgs10_m - dgs3mo_m),
            "igcredit": (dbaa_m - dgs10_m),
            "equity": (ey - dgs10_m),
            "hycredit": (baa_m - daaa_m),
            "realyld": (dgs10_m - cpi_yoy_last_known),
        }
    ).sort_index()

    Z = _trailing_z(rp, W).dropna(how="all")
    return _burn(Z)


def compute_rpv_weights(close_panel: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[dict, str, dict]:
    """Sequential filter variant: value z>0 -> SMA200 gate -> fully-invested z-weighted survivors (no per-asset cap)."""
    Z = compute_rpv_signals()
    if sig_d not in Z.index:
        valid_ds = Z.index[Z.index <= sig_d]
        if len(valid_ds) == 0:
            return {"SHV": 1.0}, "CASH", {"reason": "no_signal"}
        sig_d = valid_ds[-1]

    zrow = Z.loc[sig_d].dropna()
    prices = _build_rpv_price_panel(close_panel)

    survivors: list[tuple[str, float]] = []
    for prem, z in zrow.items():
        if z > 0:
            asset = ASSET_OF[prem]
            if _sma_above(prices, asset, sig_d, win=200):
                survivors.append((asset, float(z)))

    if not survivors:
        diag = {
            "z_scores": zrow.to_dict(),
            "base_weights": {},
            "guarded_weights": {"SHV": 1.0},
            "eligible": [],
            "reason": "no_survivors",
        }
        return {"SHV": 1.0}, "CASH", diag

    strength_total = sum(s for _, s in survivors)
    if strength_total <= 0:
        diag = {
            "z_scores": zrow.to_dict(),
            "base_weights": {},
            "guarded_weights": {"SHV": 1.0},
            "eligible": [],
            "reason": "non_positive_strength",
        }
        return {"SHV": 1.0}, "CASH", diag

    base_weights = {}
    weights = {}
    for asset, strength in sorted(survivors, key=lambda x: -x[1]):
        raw = strength / strength_total
        base_weights[asset] = base_weights.get(asset, 0.0) + raw
        weights[asset] = weights.get(asset, 0.0) + min(CAP, raw)

    invested = sum(weights.values())
    if invested < 1.0:
        weights["SHV"] = weights.get("SHV", 0.0) + (1.0 - invested)

    regime = "WEIGHTED_GUARDED" if weights.get("SHV", 0.0) < 1.0 else "CASH"
    diag = {
        "z_scores": zrow.to_dict(),
        "base_weights": base_weights,
        "guarded_weights": weights,
        "eligible": [a for a, _ in survivors],
        "reason": "ok" if regime != "CASH" else "all_cash",
    }
    return weights, regime, diag


def run_rpv_backtest(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float = COST_BPS_PER_SIDE,
) -> pd.Series:
    """Run RPV sleeve backtest using T+1 MOO close-to-close attribution."""
    prices = _build_rpv_price_panel(panel)
    if prices.empty:
        return pd.Series(dtype=float)

    Z = compute_rpv_signals()
    sig_dates = Z.index[Z.index <= end]

    full_idx = prices.loc[:end].index
    trade_idx = prices.loc[start:end].index
    daily_rets = pd.Series(0.0, index=full_idx)
    weights_for_date: dict[pd.Timestamp, dict] = {}

    for sd in sig_dates:
        target, _, _ = compute_rpv_weights(panel, sd)
        future = full_idx[full_idx > sd]
        if len(future) >= 1:
            weights_for_date[future[0]] = target

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {"SHV": 1.0}
    cur_w_idx = 0

    for ts in full_idx:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w and cost_bps > 0:
                tovr = sum(
                    abs(cur_w.get(a, 0.0) - new_w.get(a, 0.0))
                    for a in set(cur_w) | set(new_w)
                )
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1

        prev_loc = prices.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = prices.index[prev_loc - 1]

        port_r = 0.0
        for asset, w in cur_w.items():
            if asset not in prices.columns:
                continue
            today = prices.loc[ts, asset]
            yest = prices.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
        daily_rets.loc[ts] += port_r

    return daily_rets.loc[trade_idx]
