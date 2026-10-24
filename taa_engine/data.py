from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pandas as pd
import yfinance as yf


RISKY_ASSETS = ("QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC")
SAFE_ASSETS = ("BIL", "IEF")
BENCHMARKS = ("SPY", "AGG")
HAA_ASSETS = ("IWM", "VEA", "VWO", "TIP", "BIL")
BAA_ASSETS = ("BND", "VGK", "EWJ", "HYG", "LQD")
AAA_ASSETS = ("EZU", "IYR", "RWX")
VAA_ASSETS = ("GSG", "SHY")
RPV_ASSETS = ("TLT", "LQD", "SPY", "HYG", "TIP", "BIL")
TICKERS = tuple(dict.fromkeys((*RISKY_ASSETS, *SAFE_ASSETS, *BENCHMARKS, *HAA_ASSETS, *BAA_ASSETS, *AAA_ASSETS, *VAA_ASSETS, *RPV_ASSETS)))
CACHE_PATH = Path(".cache/cpm_daily_prices.csv.gz")
CACHE_OVERLAP_DAYS = 35
NDX_CACHE_PATH = Path(".cache/ndx_constituent_prices.csv.gz")
R2_PRICE_KEY = "cpm/daily-prices.csv.gz"
R2_METADATA_KEY = "cpm/daily-prices.json"


def _close_field(download: pd.DataFrame) -> pd.DataFrame:
    """Extract adjusted close, tolerating yfinance's single/multi-index shapes."""
    if isinstance(download.columns, pd.MultiIndex):
        for level in range(download.columns.nlevels):
            if "Close" in download.columns.get_level_values(level):
                return download.xs("Close", axis=1, level=level)
        raise ValueError("Yahoo response did not contain a Close field.")
    if "Close" not in download:
        raise ValueError("Yahoo response did not contain a Close field.")
    close = download["Close"]
    return close.to_frame() if isinstance(close, pd.Series) else close


def download_daily_prices(
    *, start: str = "2000-01-01", end: str | None = None,
    tickers: Sequence[str] = TICKERS, minimum_rows: int = 300,
) -> pd.DataFrame:
    """Download daily, dividend/split-adjusted closes for the requested ETFs."""
    raw = yf.download(
        list(tickers), start=start, end=end, auto_adjust=True,
        # yfinance's parallel requests can contend on its SQLite cache in CI,
        # leaving one ETF (often AGG) empty and the entire common panel unusable.
        actions=False, progress=False, threads=False,
    )
    if raw.empty:
        raise ValueError("Yahoo Finance returned no price history.")

    prices = _close_field(raw)
    prices.columns = [str(column) for column in prices.columns]
    missing = sorted(set(tickers) - set(prices.columns))
    if missing:
        raise ValueError(f"Yahoo Finance returned no data for: {', '.join(missing)}")

    prices.index = pd.DatetimeIndex(prices.index)
    if prices.index.tz is not None:
        prices.index = prices.index.tz_localize(None)
    prices = prices.loc[:, list(tickers)].sort_index()
    prices = prices.dropna(how="all")

    # CPM needs a common daily panel. Start when every required ETF has begun
    # trading, then discard any rows where one feed has a missing close.
    complete = prices.notna().all(axis=1)
    if not complete.any():
        raise ValueError("No date has prices for every requested ETF.")
    first_complete = complete[complete].index[0]
    prices = prices.loc[first_complete:].dropna(how="any")
    if len(prices) < minimum_rows:
        raise ValueError(f"Fewer than {minimum_rows} complete daily observations were downloaded.")
    return prices


def _r2_client():
    """Create an optional private Cloudflare R2 client from environment config."""
    bucket = os.getenv("CPM_R2_BUCKET")
    if not bucket:
        return None, None
    account_id = os.getenv("CPM_R2_ACCOUNT_ID")
    access_key = os.getenv("CPM_R2_ACCESS_KEY_ID")
    secret_key = os.getenv("CPM_R2_SECRET_ACCESS_KEY")
    if not all((account_id, access_key, secret_key)):
        raise ValueError("R2 cache needs CPM_R2_ACCOUNT_ID, CPM_R2_ACCESS_KEY_ID, and CPM_R2_SECRET_ACCESS_KEY.")
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Install the optional R2 dependency with `uv sync --extra r2` before using CPM_R2_BUCKET.") from exc
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    return client, bucket


def _restore_r2_cache(cache_path: Path, client, bucket: str) -> bool:
    """Restore a persisted cache pair if the local runner has no copy."""
    metadata_path = cache_path.with_suffix(cache_path.suffix + ".json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        body = client.get_object(Bucket=bucket, Key=R2_PRICE_KEY)["Body"]
        cache_path.write_bytes(body.read())
        metadata_path.write_bytes(client.get_object(Bucket=bucket, Key=R2_METADATA_KEY)["Body"].read())
        return True
    except client.exceptions.NoSuchKey:
        cache_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        return False


def _persist_r2_cache(cache_path: Path, client, bucket: str) -> None:
    metadata_path = cache_path.with_suffix(cache_path.suffix + ".json")
    client.put_object(Bucket=bucket, Key=R2_PRICE_KEY, Body=cache_path.read_bytes(), ContentType="application/gzip")
    client.put_object(Bucket=bucket, Key=R2_METADATA_KEY, Body=metadata_path.read_bytes(), ContentType="application/json")


def load_daily_prices(
    *, start: str = "2000-01-01", end: str | None = None,
    tickers: Sequence[str] = TICKERS, refresh: bool = False,
    cache_path: Path = CACHE_PATH,
) -> tuple[pd.DataFrame, str]:
    """Read the local cache, or download and replace it when missing/refreshed.

    The first run downloads the full panel. Later runs refresh only a short
    overlap plus missing dates, replacing those rows to catch delayed prices
    and recent adjustment revisions. Set refresh=True for a full rebuild.
    """
    cache_path = Path(cache_path)
    metadata_path = cache_path.with_suffix(cache_path.suffix + ".json")
    start_date = pd.Timestamp(start).date()
    requested_end = pd.Timestamp(end).date() if end else None
    r2_client, r2_bucket = _r2_client()
    if r2_client and not cache_path.exists():
        _restore_r2_cache(cache_path, r2_client, r2_bucket)

    if not refresh and cache_path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        cached_tickers = tuple(metadata.get("tickers", ()))
        cached_start = pd.Timestamp(metadata["requested_start"]).date()
        prices = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        prices.index = pd.DatetimeIndex(prices.index)
        missing = sorted(set(tickers) - set(prices.columns))
        if missing:
            # Add newly requested symbols to an existing cache without redownloading
            # the established price panel.
            patch_start = max(pd.Timestamp(start), prices.index[0])
            added = download_daily_prices(
                start=patch_start.strftime("%Y-%m-%d"), end=end,
                tickers=missing, minimum_rows=1,
            )
            prices = prices.join(added, how="outer").sort_index()
            metadata["tickers"] = list(tickers)
            metadata["fetched_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            prices = prices.reindex(columns=list(tickers)).dropna(how="any")
            prices.to_csv(cache_path, compression="gzip", index_label="date")
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
            if r2_client:
                _persist_r2_cache(cache_path, r2_client, r2_bucket)
            cached_tickers = tuple(metadata["tickers"])
        # Drop retired symbols from a superset cache without redownloading the
        # remaining histories for assets no longer used by the active strategies.
        if set(prices.columns) - set(tickers):
            prices = prices.reindex(columns=list(tickers))
            metadata["tickers"] = list(tickers)
            prices.to_csv(cache_path, compression="gzip", index_label="date")
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
            if r2_client:
                _persist_r2_cache(cache_path, r2_client, r2_bucket)
            cached_tickers = tuple(tickers)
        compatible = set(tickers).issubset(cached_tickers) and cached_start <= start_date
        cached_last = prices.index[-1].date() if not prices.empty else None
        already_covers_end = requested_end is not None and cached_last is not None and cached_last >= requested_end
        if compatible and already_covers_end:
            prices = prices.loc[prices.index < pd.Timestamp(end)]
            return prices.loc[:, list(tickers)], f"cache fetched {metadata['fetched_at_utc']}"
        if compatible:
            old_last = prices.index[-1]
            overlap_start = max(pd.Timestamp(start), old_last - pd.Timedelta(days=CACHE_OVERLAP_DAYS))
            patch = download_daily_prices(
                start=overlap_start.strftime("%Y-%m-%d"), end=end,
                tickers=tickers, minimum_rows=1,
            )
            prices = pd.concat([prices.loc[prices.index < patch.index[0]], patch])
            prices = prices.loc[~prices.index.duplicated(keep="last")].sort_index()
            if end:
                prices = prices.loc[prices.index < pd.Timestamp(end)]
            status = f"updated from {patch.index[0].date()} through {prices.index[-1].date()}"
        else:
            prices = download_daily_prices(start=start, end=end, tickers=tickers)
            status = f"downloaded full history through {prices.index[-1].date()}"
    else:
        prices = download_daily_prices(start=start, end=end, tickers=tickers)
        status = f"downloaded full history through {prices.index[-1].date()}"

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = {
        "source": "yfinance",
        "adjusted": True,
        "tickers": list(tickers),
        "requested_start": str(start_date),
        "requested_end": str(requested_end) if requested_end else None,
        "first_price_date": prices.index[0].date().isoformat(),
        "last_price_date": prices.index[-1].date().isoformat(),
        "fetched_at_utc": fetched_at,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_prices = cache_path.with_name(cache_path.name + ".tmp")
    temp_metadata = metadata_path.with_name(metadata_path.name + ".tmp")
    prices.to_csv(temp_prices, compression="gzip", index_label="date")
    temp_metadata.write_text(json.dumps(metadata, indent=2) + "\n")
    temp_prices.replace(cache_path)
    temp_metadata.replace(metadata_path)
    if r2_client:
        _persist_r2_cache(cache_path, r2_client, r2_bucket)
        status += " (private R2 cache saved)"
    return prices.loc[:, list(tickers)], f"{status}; fetched {fetched_at}"


def load_ndx_constituent_prices(
    *, start: str = "2007-01-01", end: str | None = None, refresh: bool = False,
    cache_path: Path = NDX_CACHE_PATH,
) -> tuple[pd.DataFrame, str]:
    """Load adjusted daily prices for the historical PIT Nasdaq-100 universe.

    Membership is sampled monthly. We retain the union of all historical members
    in a separate cache so the ETF panel remains compact and survivorship bias is
    avoided. A first run can be large; later runs update only the recent tail.
    """
    try:
        import index_constitution as ic
    except ImportError as exc:
        raise RuntimeError("NDX requires index-constitution; install project dependencies with `uv sync`.") from exc

    cache_path = Path(cache_path)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    cached = pd.DataFrame()
    if not refresh and cache_path.exists():
        cached = pd.read_csv(cache_path, index_col=0, parse_dates=True).sort_index()

    # Monthly PIT snapshots keep the universe tied to information available at
    # each rebalance; current constituents are never backfilled into the past.
    snapshots = pd.date_range(start_ts, end_ts, freq="ME")
    if not len(snapshots) or snapshots[-1] < end_ts:
        snapshots = snapshots.append(pd.DatetimeIndex([end_ts]))
    members: set[str] = set(map(str, cached.columns))
    for date in snapshots:
        constituents = ic.constituents_at("nasdaq100", date.strftime("%Y-%m-%d"))
        members.update(map(str, constituents["symbol"].dropna().unique()))
    tickers = sorted(members)
    cached_symbols = set(map(str, cached.columns))
    cache_covers_start = not cached.empty and cached.index[0] <= start_ts
    new_symbols = [ticker for ticker in tickers if ticker not in cached_symbols]
    full_history_symbols = tickers if refresh or cached.empty or not cache_covers_start else new_symbols
    tail_symbols = [] if refresh or cached.empty or not cache_covers_start else [ticker for ticker in tickers if ticker in cached_symbols]

    def fetch_symbols(symbols: list[str], fetch_start: str) -> pd.DataFrame:
        batches = []
        for offset in range(0, len(symbols), 30):
            chunk = symbols[offset:offset + 30]
            raw = yf.download(
                chunk, start=fetch_start, end=end, auto_adjust=True, actions=False,
                progress=False, threads=True, group_by="ticker", timeout=60,
            )
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                close_level = next((level for level in range(raw.columns.nlevels) if "Close" in raw.columns.get_level_values(level)), None)
                if close_level is None:
                    continue
                batch = raw.xs("Close", axis=1, level=close_level)
            else:
                batch = raw["Close"].to_frame(name=chunk[0]) if "Close" in raw else raw
            if isinstance(batch, pd.Series):
                batch = batch.to_frame(name=chunk[0])
            batches.append(batch)
        return pd.concat(batches, axis=1) if batches else pd.DataFrame()

    fresh_frames = []
    if full_history_symbols:
        fresh_frames.append(fetch_symbols(full_history_symbols, start))
    if tail_symbols:
        tail_start = max(start_ts, cached.index[-1] - pd.Timedelta(days=CACHE_OVERLAP_DAYS)).strftime("%Y-%m-%d")
        fresh_frames.append(fetch_symbols(tail_symbols, tail_start))
    fresh = pd.concat(fresh_frames, axis=1) if fresh_frames else pd.DataFrame()
    if not fresh.empty:
        fresh.columns = [str(col) for col in fresh.columns]
        fresh.index = pd.DatetimeIndex(fresh.index)
        if fresh.index.tz is not None:
            fresh.index = fresh.index.tz_localize(None)
        if cached.empty:
            cached = fresh.sort_index()
        else:
            cached = cached.reindex(
                index=cached.index.union(fresh.index),
                columns=cached.columns.union(fresh.columns),
            ).sort_index()
            cached.update(fresh)
    if cached.empty:
        raise ValueError("No cached or newly downloaded Nasdaq-100 prices are available.")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached.to_csv(cache_path, compression="gzip", index_label="date")
    return cached.loc[(cached.index >= start_ts) & (cached.index < end_ts)], f"PIT universe prices cached through {cached.index[-1].date()} ({len(cached.columns)} symbols)"
