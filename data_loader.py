"""Unified data access layer for CPM, NDX, RPV, and Value sleeves."""
from __future__ import annotations

import functools
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# Proxy panel paths
LOCAL_PROXY = DATA_DIR / "proxy_adjusted_close_daily.csv"
ARTIFACTS_PROXY = ROOT.parent / "artifacts" / "cpa-1997-exact-core-proxy-research" / "proxy_adjusted_close_daily.csv"
PROXY_PATH = LOCAL_PROXY if LOCAL_PROXY.exists() else ARTIFACTS_PROXY

# NDX paths
NDX_PRICES_FILE = DATA_DIR / "ndx_constituents" / "prices.parquet"

# Macro open paths
OPEN_CACHE = DATA_DIR / "macro_opens"
OPEN_CACHE_INTRADAY_SANITY_MAX = 0.50
OHLC_TICKERS = ["SPY", "QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC", "SHV", "IEF", "HYG", "TIP"]


# ===========================================================================
# 1. Core CPM Panel Loader
# ===========================================================================

def _download_adjusted_close(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Download adjusted close series (same convention as stitched history)."""
    d = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        threads=False,
        timeout=30,
    )
    if d is None or d.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(d.columns, pd.MultiIndex):
        if "Close" in d.columns.get_level_values(-1):
            c = d.xs("Close", axis=1, level=-1)
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
        else:
            c = d.iloc[:, 0]
    else:
        if "Close" in d.columns:
            c = d["Close"]
        else:
            c = d.iloc[:, 0]
    c.index = pd.to_datetime(c.index)
    c.index.name = "Date"
    return c.dropna().sort_index()


def _fetch_cached_adjusted_close(ticker: str, start: pd.Timestamp, end: pd.Timestamp, cache_dir: str) -> pd.Series:
    """Retrieve from local cache or download on cache miss."""
    os.makedirs(cache_dir, exist_ok=True)
    fpath = Path(cache_dir) / f"{ticker}_adjusted_close.parquet"
    if fpath.exists():
        try:
            s = pd.read_parquet(fpath)["Close"]
            s.index = pd.to_datetime(s.index)
            s.index.name = "Date"
            if not s.empty and s.index.min() <= start and s.index.max() >= end - pd.Timedelta(days=1):
                return s.loc[start:end]
        except Exception:
            pass

    s = _download_adjusted_close(ticker, start, end)
    if not s.empty:
        pd.DataFrame({"Close": s}).to_parquet(fpath)
    return s.loc[start:end]


def _assert_live_panel_fresh(df: pd.DataFrame, reference_date: pd.Timestamp, required_assets: list[str]) -> None:
    """Assert that all required assets have fresh data up to reference_date."""
    ref_ts = pd.Timestamp(reference_date).normalize()
    stale_assets = []
    for asset in required_assets:
        if asset not in df.columns:
            stale_assets.append((asset, None))
            continue
        col = df[asset]
        last_valid = col.last_valid_index()
        if last_valid is None:
            stale_assets.append((asset, None))
            continue
        last_ts = pd.Timestamp(last_valid).normalize()
        diff_days = (ref_ts - last_ts).days
        if diff_days > 5:
            stale_assets.append((asset, last_valid))

    if stale_assets:
        stale_msg = ", ".join(
            f"{asset}={(lv.date().isoformat() if lv is not None else 'missing')}"
            for asset, lv in stale_assets
        )
        raise ValueError(
            f"Live panel stale at reference_date={ref_ts.date().isoformat()}; "
            f"expected last-valid >= reference_date - 5 days. Stale: {stale_msg}"
        )


def load_panel(start: pd.Timestamp = None, end: pd.Timestamp = None,
               cache_dir: str = "/tmp/cpm_cache", live: bool = False) -> pd.DataFrame:
    """Build the daily price panel from all sources."""
    import cpm_live  # Lazy import to avoid cyclic dependency
    
    os.makedirs(cache_dir, exist_ok=True)

    if PROXY_PATH.exists():
        panel = pd.read_csv(PROXY_PATH, parse_dates=["Date"], index_col="Date").sort_index()
    else:
        panel = pd.DataFrame()

    for fname, col in [
        ("gld_stitched_extended_daily.csv", "GLD"),
        ("tip_stitched_daily.csv", "TIP"),
        ("hyg_stitched_daily.csv", "HYG"),
        ("lqd_stitched_daily.csv", "LQD"),
        ("shv_stitched_daily.csv", "SHV"),
        ("ief_stitched_daily.csv", "IEF"),
        ("tlt_stitched_daily.csv", "TLT"),
        ("qqq_stitched_daily.csv", "QQQ"),
    ]:
        fpath = DATA_DIR / fname
        if fpath.exists():
            s = pd.read_csv(fpath, parse_dates=[0], index_col=0)
            s.columns = [col]
            if panel.empty:
                panel = s.copy()
            elif col in panel.columns:
                panel = panel.drop(columns=[col]).join(s, how="outer").sort_index()
            else:
                panel = panel.join(s, how="outer").sort_index()

    needed = sorted(set(cpm_live.RISKY_UNIVERSE + cpm_live.SAFE_POOL + cpm_live.CANARY_ASSETS + cpm_live.PP_ASSETS + [cpm_live.DEFAULT_CASH, "LQD"]))
    present = set(panel.columns)
    missing = [t for t in needed if t not in present]

    pull_start = (start - pd.DateOffset(years=2)) if start else pd.Timestamp("1995-01-01")
    pull_end = end if end else pd.Timestamp.today() + pd.Timedelta(days=1)

    fetched_missing = {}
    for t in missing:
        try:
            s = _fetch_cached_adjusted_close(t, pull_start, pull_end, cache_dir)
            if not s.empty:
                fetched_missing[t] = s
        except Exception as e:
            print(f"WARN: could not fetch {t}: {e}", file=sys.stderr)

    if fetched_missing:
        extras = pd.DataFrame(fetched_missing)
        panel = panel.join(extras, how="outer").sort_index() if not panel.empty else extras

    if live and not panel.empty:
        for t in [x for x in needed if x in panel.columns]:
            col = panel[t]
            last_valid = col.last_valid_index()
            delta_start = pull_start if last_valid is None else last_valid
            if delta_start > pull_end:
                continue
            try:
                delta = _fetch_cached_adjusted_close(t, delta_start, pull_end, cache_dir)
                if delta.empty:
                    continue

                if last_valid is None:
                    panel = panel.reindex(panel.index.union(delta.index))
                    panel.loc[delta.index, t] = delta.values
                    continue

                ratio_date = None
                if last_valid in delta.index and pd.notna(delta.loc[last_valid]) and delta.loc[last_valid] != 0:
                    ratio_date = last_valid
                else:
                    overlap = col.dropna().index.intersection(delta.index)
                    for d in overlap:
                        if pd.notna(col.loc[d]) and pd.notna(delta.loc[d]) and delta.loc[d] != 0:
                            ratio_date = d
                            break

                if ratio_date is not None:
                    ratio = col.loc[ratio_date] / delta.loc[ratio_date]
                    delta = delta * ratio

                new_idx = delta.index[delta.index > last_valid]
                if len(new_idx) == 0:
                    continue

                prev_val = col.loc[last_valid]
                first_new_val = delta.loc[new_idx[0]]
                if pd.notna(prev_val) and prev_val != 0 and pd.notna(first_new_val):
                    first_ret = first_new_val / prev_val - 1.0
                    if abs(first_ret) > 0.50:
                        print(f"WARN: rejected live refresh for {t}; return {first_ret:+.2%} > 50%", file=sys.stderr)
                        continue

                panel = panel.reindex(panel.index.union(new_idx))
                panel.loc[new_idx, t] = delta.loc[new_idx].values
            except Exception as e:
                print(f"WARN: could not refresh {t}: {e}", file=sys.stderr)

    if start:
        panel = panel[panel.index >= start - pd.DateOffset(months=15)]

    if live:
        if end is not None:
            panel = panel[panel.index <= end]
            reference_date = min(pd.Timestamp(end).normalize(), pd.Timestamp.today().normalize())
        else:
            reference_date = pd.Timestamp.today().normalize()
        required_assets = list(dict.fromkeys(cpm_live.RISKY_UNIVERSE + cpm_live.SAFE_POOL + cpm_live.CANARY_ASSETS))
        _assert_live_panel_fresh(panel, reference_date=reference_date, required_assets=required_assets)
    else:
        cap_end = cpm_live.EVAL_END if end is None else min(pd.Timestamp(end), cpm_live.EVAL_END)
        panel = panel.loc[:cap_end]
        if cap_end == cpm_live.EVAL_END:
            required_assets = list(dict.fromkeys(cpm_live.RISKY_UNIVERSE + cpm_live.SAFE_POOL + cpm_live.CANARY_ASSETS))
            stale_assets = []
            for asset in required_assets:
                if asset not in panel.columns:
                    stale_assets.append((asset, None))
                    continue
                last_valid = panel[asset].last_valid_index()
                if last_valid is None or last_valid < cpm_live.EVAL_END:
                    stale_assets.append((asset, last_valid))
            if stale_assets:
                stale_msg = ", ".join(
                    f"{asset}={(lv.date().isoformat() if lv is not None else 'missing')}"
                    for asset, lv in stale_assets
                )
                raise ValueError(f"Frozen panel stale at EVAL_END; {stale_msg}")

    return panel.sort_index()


# ===========================================================================
# 2. NDX Panel Loader
# ===========================================================================

def load_ndx_panel() -> pd.DataFrame:
    """Load NDX constituent prices from disk."""
    return pd.read_parquet(NDX_PRICES_FILE)


# ===========================================================================
# 3. Macro Open/Close Loader
# ===========================================================================

def _assert_open_cache_adjusted(opens_df, closes_df, threshold=OPEN_CACHE_INTRADAY_SANITY_MAX):
    intraday_abs = (closes_df / opens_df - 1.0).abs().replace([np.inf, -np.inf], np.nan)
    bad_mask = intraday_abs > threshold
    if not bool(bad_mask.to_numpy().any()):
        return
    bad = intraday_abs.where(bad_mask).stack(dropna=True)
    dt, ticker = bad.idxmax()
    val = float(bad.max())
    raise ValueError(
        f"Open-cache contamination detected: {ticker} {pd.Timestamp(dt).date()} has "
        f"|close/open - 1|={val:.2%} (>{threshold:.0%}) in {OPEN_CACHE}. "
        "Regenerate cache with yfinance auto_adjust=True."
    )


def load_open_close() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (open_df, close_df) of REAL yfinance auto_adjust OHLC, aligned union index."""
    def _normalize_ohlc(df):
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "Close"])
        if isinstance(df.columns, pd.MultiIndex):
            lvl0 = df.columns.get_level_values(0)
            lvl1 = df.columns.get_level_values(1)
            if "Open" in lvl0 and "Close" in lvl0:
                df.columns = lvl0
            elif "Open" in lvl1 and "Close" in lvl1:
                df.columns = lvl1
            else:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        if "Open" not in df.columns or "Close" not in df.columns:
            return pd.DataFrame(columns=["Open", "Close"])
        out = df[["Open", "Close"]].dropna().copy()
        out.index = pd.to_datetime(out.index)
        out.index.name = "Date"
        return out.sort_index()

    opens, closes = {}, {}
    for t in OHLC_TICKERS:
        p = OPEN_CACHE / f"{t}.csv"
        if p.exists():
            d = _normalize_ohlc(pd.read_csv(p, parse_dates=[0], index_col=0))
            if d.empty:
                raise ValueError(f"Macro open cache {p} exists but missing Open/Close data.")
        else:
            try:
                d = _normalize_ohlc(
                    yf.download(
                        t,
                        start="1999-01-01",
                        auto_adjust=True,
                        progress=False,
                        threads=False,
                        timeout=30,
                    )
                )
            except Exception:
                d = pd.DataFrame(columns=["Open", "Close"])
            if d.empty:
                continue

        opens[t] = d["Open"]
        closes[t] = d["Close"]

    opens_df = pd.DataFrame(opens).sort_index()
    closes_df = pd.DataFrame(closes).sort_index()
    _assert_open_cache_adjusted(opens_df, closes_df)
    return opens_df, closes_df


# ===========================================================================
# 4. Fundamental Valuein Loader
# ===========================================================================

@functools.lru_cache(maxsize=1)
def load_valuein_cache(cache_dir: str = "data/valuein") -> tuple[dict, dict]:
    """Loads local parquet files: fact, security and builds FLOWS and BS dicts."""
    import value_sleeve_live  # Lazy import
    
    fact = pd.read_parquet(Path(cache_dir) / "fact.parquet")
    sec = pd.read_parquet(Path(cache_dir) / "security.parquet")
    prim = sec[sec.is_primary_ticker][["entity_id", "symbol"]].drop_duplicates("entity_id")
    e2t = dict(zip(prim.entity_id, prim.symbol))

    fact = fact[fact.entity_id.isin(e2t)].copy()
    fact["ticker"] = fact.entity_id.map(e2t)
    fact["accepted"] = pd.to_datetime(fact["accepted_at"]).dt.tz_localize(None).dt.normalize()
    fact["period_end"] = pd.to_datetime(fact["period_end"])
    
    fact = fact.sort_values("accepted")
    fact = fact.drop_duplicates(
        subset=["ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end"],
        keep="first"
    )
    
    FLOWS = value_sleeve_live._build_pit_flows(fact)
    BS = value_sleeve_live._build_pit_bs(fact)
    return FLOWS, BS


# ===========================================================================
# 5. FRED Macro Loader
# ===========================================================================

def _read_csv_url_timeout(url: str, timeout_s: float = 15.0) -> pd.DataFrame:
    with urlopen(url, timeout=timeout_s) as response:
        text = response.read().decode("utf-8")
    return pd.read_csv(io.StringIO(text))


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
    fallback_paths = fallback_paths or [DATA_DIR / f"fred_{id_}.csv"]

    if os.environ.get("REFRESH_FRED") == "1":
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
        try:
            return _parse_fred_series(_read_csv_url_timeout(url, timeout_s=15.0), id_)
        except Exception:
            pass

    for fpath in fallback_paths:
        if fpath.exists():
            return _parse_fred_series(pd.read_csv(fpath), id_)
    raise FileNotFoundError(f"FRED series {id_} not found locally.")


def load_macro_data() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Load base macro series used by term/igcredit/equity premia."""
    dgs10 = _fetch_fred_series("DGS10")
    dgs3mo = _fetch_fred_series("DGS3MO")
    dbaa = _fetch_fred_series("DBAA")

    try:
        sp500 = _fetch_fred_series("SP500")
    except Exception:
        sp500 = pd.Series(dtype=float, index=pd.DatetimeIndex([]))

    fpath_earnings = DATA_DIR / "sp500_earnings.csv"
    try:
        df_earn = pd.read_csv(fpath_earnings)
    except Exception:
        if os.environ.get("REFRESH_FRED") == "1":
            url_earnings = "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv"
            df_earn = _read_csv_url_timeout(url_earnings, timeout_s=15.0)
        else:
            raise FileNotFoundError("S&P 500 earnings file not found locally and REFRESH_FRED not set.")

    df_earn["Date"] = pd.to_datetime(df_earn["Date"])
    df_earn = df_earn.set_index("Date").sort_index()

    E = pd.to_numeric(df_earn["Earnings"], errors="coerce")
    E = E.where(E > 0, np.nan).ffill().dropna()
    P = pd.to_numeric(df_earn["SP500"], errors="coerce").dropna()

    return dgs10, dgs3mo, dbaa, sp500, E, P
