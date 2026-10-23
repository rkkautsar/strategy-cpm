from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .strategies import NDX_SAFE, _events_from_signals


VALUEIN_CACHE = Path(os.environ.get("VALUEIN_CACHE_DIR", ".cache/valuein"))
FLOW_CONCEPTS = ("TotalRevenue", "NetIncome", "GrossProfit", "OperatingIncome", "OperatingCashFlow", "CAPEX")
BS_CONCEPTS = ("TotalAssets", "TotalLiabilities", "StockholdersEquity", "ShortTermDebt", "LongTermDebt", "CommonSharesOutstanding")
SELECT_K = 5
START_DATE = pd.Timestamp("2010-06-01")
RECYCLED_FUND_SYMBOLS = {"BBBY", "LIFE", "GOLD", "BATRA"}
_SPLITS_PATH = VALUEIN_CACHE / "splits_calendar.json"
_COVERED_PATH = VALUEIN_CACHE / "splits_covered_manifest.json"
_SPLIT_CAL = {
    ticker: [(pd.Timestamp(date), float(factor)) for date, factor in records]
    for ticker, records in json.loads(_SPLITS_PATH.read_text()).items()
} if _SPLITS_PATH.exists() else {}
_COVERED_TICKERS = set(json.loads(_COVERED_PATH.read_text()).get("covered", [])) if _COVERED_PATH.exists() else set()
VALUEIN_API = "https://data.valuein.biz"
VALUEIN_REFRESH_PATH = "valuein_refresh.json"


def _valuein_response(url: str, token: str, *, json_response: bool):
    """Fetch one Valuein response with bounded retries and no credential logging."""
    request = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json" if json_response else "application/octet-stream",
        "User-Agent": "taa-engine-valuein-refresh/1.0",
    })
    for attempt in range(4):
        try:
            with urlopen(request, timeout=90) as response:
                body = response.read()
            return json.loads(body) if json_response else body
        except HTTPError as exc:
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "unknown")
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = None
                if delay is not None and attempt < 3 and 0 <= delay <= 300:
                    delay = int(delay) + 1
                    print(f"Valuein rate limited this request; retrying after {delay}s", flush=True)
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Valuein daily request quota reached; retry after {retry_after} seconds. "
                    "Any completed CIK partitions are checkpointed; rerun after the quota resets."
                ) from exc
            if 500 <= exc.code < 600 and attempt < 3:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(f"Valuein request failed with HTTP {exc.code} for {url.split('/v1/')[-1]}.") from exc
        except URLError as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Valuein request failed: {exc.reason}") from exc
    raise RuntimeError("Valuein request failed after retries.")


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.stem}.refresh.parquet")
    frame.to_parquet(temp_path, index=False)
    temp_path.replace(path)


def _atomic_json(payload: dict, path: Path) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _normalize_cik(values: pd.Series) -> pd.Series:
    return values.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(10)


def refresh_valuein_cache(
    cache_dir: Path = VALUEIN_CACHE,
    *,
    as_of: pd.Timestamp,
    required: bool = False,
    max_partitions: int = 100,
) -> str:
    """Refresh only changed Valuein snapshots and current Nasdaq-100 fact partitions.

    Valuein exposes full company partitions rather than row cursors. We therefore
    replace each current Nasdaq-100 CIK's complete fact partition when the global
    snapshot changes. Successfully downloaded partitions are checkpointed so a
    quota limit or interrupted run can resume without repeating completed work.
    """
    cache_dir = Path(cache_dir)
    token = os.getenv("VALUEIN_API_KEY", "").strip()
    if not token:
        if required:
            raise RuntimeError("Monthly builds require VALUEIN_API_KEY to refresh VAL fundamentals.")
        return "skipped (VALUEIN_API_KEY is not configured)"

    fact_path = cache_dir / "fact.parquet"
    security_path = cache_dir / "security.parquet"
    metadata_path = cache_dir / VALUEIN_REFRESH_PATH
    if not fact_path.exists() or not security_path.exists():
        raise FileNotFoundError(
            f"Valuein incremental refresh needs a private bootstrap cache containing "
            f"{fact_path.name} and {security_path.name}; it will not silently download a full market snapshot."
        )
    if max_partitions < 1:
        raise ValueError("VALUEIN_MAX_PARTITION_DOWNLOADS must be at least 1.")

    account = _valuein_response(f"{VALUEIN_API}/v1/me", token, json_response=True)
    plan = str(account.get("plan", "")).lower()
    if str(account.get("status", "")).lower() != "active" or plan not in {"sp500", "pro", "full"}:
        raise RuntimeError(
            f"Valuein plan '{plan or 'unknown'}' cannot provide fundamentals for VAL; "
            "an active S&P 500, Pro, or Full plan is required."
        )
    manifest = _valuein_response(f"{VALUEIN_API}/v1/manifest", token, json_response=True)
    snapshot = str(manifest.get("snapshot", ""))
    if not snapshot:
        raise RuntimeError("Valuein manifest did not include a snapshot identifier.")
    tables = set(manifest.get("tables", []))
    if not {"fact", "security"}.issubset(tables):
        raise RuntimeError("Valuein plan manifest does not include both fact and security tables.")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    metadata.setdefault("partition_snapshots", {})

    if metadata.get("security_snapshot") != snapshot or metadata.get("plan") != plan:
        security_bytes = _valuein_response(
            f"{VALUEIN_API}/v1/{plan}/security", token, json_response=False,
        )
        security = pd.read_parquet(BytesIO(security_bytes))
        if security.empty:
            raise RuntimeError("Valuein returned an empty security table; the existing cache was preserved.")
        cik_col = "entity_id" if "entity_id" in security else "cik" if "cik" in security else None
        symbol_col = "symbol" if "symbol" in security else "ticker" if "ticker" in security else None
        if cik_col is None or symbol_col is None:
            raise RuntimeError("Valuein security table is missing its CIK or ticker columns.")
        security[cik_col] = _normalize_cik(security[cik_col])
        _atomic_parquet(security, security_path)
        metadata.update({"plan": plan, "security_snapshot": snapshot})
        metadata["security_columns"] = {"cik": cik_col, "symbol": symbol_col}
        _atomic_json(metadata, metadata_path)

    security = pd.read_parquet(security_path)
    cik_col = "entity_id" if "entity_id" in security else "cik" if "cik" in security else None
    symbol_col = "symbol" if "symbol" in security else "ticker" if "ticker" in security else None
    if cik_col is None or symbol_col is None:
        raise RuntimeError("Cached Valuein security table is missing its CIK or ticker columns.")
    active = security.copy()
    if "is_active" in active:
        active_flag = active.is_active.astype(str).str.lower().isin({"true", "1", "yes"})
        active = active[active_flag]
    active = active.assign(
        _cik=_normalize_cik(active[cik_col]),
        _symbol=active[symbol_col].astype(str).str.upper(),
    )

    try:
        import index_constitution as ic
        constituent_frame = ic.constituents_at("nasdaq100", pd.Timestamp(as_of).strftime("%Y-%m-%d"))
    except Exception as exc:
        raise RuntimeError(f"Could not resolve point-in-time Nasdaq-100 members for Valuein refresh: {exc}") from exc
    if "symbol" not in constituent_frame:
        raise RuntimeError("Nasdaq-100 constituent data did not include a symbol column.")
    members = sorted(set(constituent_frame.symbol.dropna().astype(str).str.upper()))
    ciks_by_symbol: dict[str, set[str]] = {}
    for row in active[["_symbol", "_cik"]].itertuples(index=False, name=None):
        ciks_by_symbol.setdefault(row[0], set()).add(row[1])
    ambiguous = [ticker for ticker in members if len(ciks_by_symbol.get(ticker, set())) > 1]
    if ambiguous:
        preview = ", ".join(ambiguous[:12])
        raise RuntimeError(f"Valuein {plan} security snapshot has ambiguous CIK mappings for {preview}.")
    covered_members = [ticker for ticker in members if len(ciks_by_symbol.get(ticker, set())) == 1]
    uncovered_members = sorted(set(members) - set(covered_members))
    if uncovered_members and plan != "sp500":
        preview = ", ".join(uncovered_members[:12])
        raise RuntimeError(
            f"Valuein {plan} security snapshot cannot map {len(uncovered_members)} current Nasdaq-100 tickers "
            f"to one CIK ({preview}); refresh aborted to avoid incomplete fundamentals."
        )
    if not covered_members:
        raise RuntimeError(f"Valuein {plan} security snapshot contains no current Nasdaq-100 constituents.")
    current_ciks = sorted({next(iter(ciks_by_symbol[ticker])) for ticker in covered_members})
    partition_snapshots = metadata["partition_snapshots"]
    pending = [
        cik for cik in current_ciks
        if partition_snapshots.get(cik) != {"snapshot": snapshot, "plan": plan}
    ]
    if not pending:
        metadata.update({
            "plan": plan, "snapshot": snapshot, "last_updated": manifest.get("last_updated"),
            "last_checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "current_nasdaq100_symbols": covered_members,
            "uncovered_nasdaq100_symbols": uncovered_members,
        })
        _atomic_json(metadata, metadata_path)
        suffix = f"; {len(uncovered_members)} NDX symbols outside Valuein {plan} coverage" if uncovered_members else ""
        return f"unchanged ({snapshot}; {len(current_ciks)} covered current Nasdaq-100 CIKs already current{suffix})"

    if len(pending) > max_partitions:
        batch = pending[:max_partitions]
        deferred = len(pending) - max_partitions
    else:
        batch = pending
        deferred = 0
    base_fact = pd.read_parquet(fact_path) if any(not (cache_dir / "fact_partitions" / f"{cik}.parquet").exists() for cik in batch) else None
    if base_fact is not None:
        base_fact["entity_id"] = _normalize_cik(base_fact["entity_id"])
    for offset, cik in enumerate(batch, start=1):
        fact_bytes = _valuein_response(
            f"{VALUEIN_API}/v1/{plan}/fact/{cik}.parquet", token, json_response=False,
        )
        partition = pd.read_parquet(BytesIO(fact_bytes))
        if partition.empty or "entity_id" not in partition:
            raise RuntimeError(f"Valuein returned no usable fact rows for Nasdaq-100 CIK {cik}; refresh aborted.")
        partition["entity_id"] = _normalize_cik(partition["entity_id"])
        if set(partition["entity_id"].unique()) != {cik}:
            raise RuntimeError(f"Valuein fact partition for CIK {cik} contained unexpected entity IDs.")
        required_columns = {
            "standard_concept", "period_start", "period_end", "fiscal_year", "fiscal_period",
            "accepted_at", "value_as_filed",
        }
        if missing_columns := required_columns - set(partition.columns):
            raise RuntimeError(f"Valuein fact partition for CIK {cik} is missing columns: {', '.join(sorted(missing_columns))}.")

        partition_path = cache_dir / "fact_partitions" / f"{cik}.parquet"
        prior = (
            pd.read_parquet(partition_path)
            if partition_path.exists()
            else base_fact.loc[base_fact.entity_id == cik].copy()
        )
        if not prior.empty:
            prior["entity_id"] = _normalize_cik(prior["entity_id"])
            prior["period_end"] = pd.to_datetime(prior["period_end"])
            partition["period_end"] = pd.to_datetime(partition["period_end"])
            # Retain older bootstrap history when a plan's partition has a
            # shorter lookback, so refreshes do not erase the backtest's early years.
            earliest_remote_period = partition.period_end.min()
            partition = pd.concat([
                prior.loc[prior.period_end < earliest_remote_period], partition,
            ], ignore_index=True)
        _atomic_parquet(partition, partition_path)
        partition_snapshots[cik] = {"snapshot": snapshot, "plan": plan}
        metadata.update({
            "plan": plan, "security_snapshot": snapshot,
            "last_partition_cik": cik,
            "last_partition_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        _atomic_json(metadata, metadata_path)
        if offset == 1 or offset % 10 == 0 or offset == len(batch):
            print(f"Valuein refreshed {offset}/{len(batch)} CIK partitions")

    if deferred:
        raise RuntimeError(
            f"Valuein refresh checkpointed {len(batch)} CIK partitions; {deferred} remain for snapshot {snapshot}. "
            "Rerun after the API quota resets to finish before publishing the dashboard."
        )
    metadata.update({
        "plan": plan, "snapshot": snapshot, "last_updated": manifest.get("last_updated"),
        "last_refreshed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current_nasdaq100_ciks": current_ciks,
        "current_nasdaq100_symbols": covered_members,
        "uncovered_nasdaq100_symbols": uncovered_members,
    })
    _atomic_json(metadata, metadata_path)
    suffix = f"; {len(uncovered_members)} NDX symbols outside Valuein {plan} coverage" if uncovered_members else ""
    return f"refreshed {len(batch)} covered Nasdaq-100 CIK partitions to {snapshot}{suffix}"


def load_valuein_cache(cache_dir: Path = VALUEIN_CACHE) -> tuple[dict, dict, str]:
    """Load local as-filed Valuein/EDGAR parquet snapshots and report their vintage."""
    cache_dir = Path(cache_dir)
    required = ("fact.parquet", "security.parquet")
    missing = [name for name in required if not (cache_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing Valuein cache files in {cache_dir}: {', '.join(missing)}. "
            "Set VALUEIN_CACHE_DIR to a directory containing fact.parquet and security.parquet."
        )

    fact = pd.read_parquet(cache_dir / "fact.parquet")
    security = pd.read_parquet(cache_dir / "security.parquet")
    fact_partitions = cache_dir / "fact_partitions"
    if fact_partitions.exists():
        fact["entity_id"] = _normalize_cik(fact["entity_id"])
        for partition_path in sorted(fact_partitions.glob("*.parquet")):
            partition = pd.read_parquet(partition_path)
            if partition.empty or "entity_id" not in partition:
                raise ValueError(f"Invalid Valuein fact partition: {partition_path.name}")
            partition["entity_id"] = _normalize_cik(partition["entity_id"])
            fact = pd.concat([
                fact.loc[~fact.entity_id.isin(partition.entity_id.unique())], partition,
            ], ignore_index=True)
    fact["_src"] = 0
    fact_edgar_path = cache_dir / "fact_edgar.parquet"
    security_edgar_path = cache_dir / "security_edgar.parquet"
    fact_edgar = pd.read_parquet(fact_edgar_path) if fact_edgar_path.exists() else None
    security_edgar = pd.read_parquet(security_edgar_path) if security_edgar_path.exists() else None

    if security_edgar is not None:
        bad_ids = set(security_edgar.loc[security_edgar["symbol"].isin(RECYCLED_FUND_SYMBOLS), "entity_id"])
        security_edgar = security_edgar[~security_edgar["entity_id"].isin(bad_ids)]
        if fact_edgar is not None:
            fact_edgar = fact_edgar[~fact_edgar["entity_id"].isin(bad_ids)]
    if fact_edgar is not None:
        fact_edgar = fact_edgar.copy()
        fact_edgar["_src"] = 1
        fact = pd.concat([fact, fact_edgar], ignore_index=True)
    if security_edgar is not None:
        security = pd.concat([security, security_edgar], ignore_index=True)

    primary = security[security["is_primary_ticker"]].drop_duplicates("entity_id")
    entity_to_ticker = dict(zip(primary["entity_id"], primary["symbol"].astype(str)))
    fact = fact[fact["entity_id"].isin(entity_to_ticker)].copy()
    fact["ticker"] = fact["entity_id"].map(entity_to_ticker)
    accepted = pd.to_datetime(fact["accepted_at"], utc=True)
    if accepted.dt.tz is not None:
        accepted = accepted.dt.tz_localize(None)
    fact["accepted"] = accepted.dt.normalize()
    fact["period_end"] = pd.to_datetime(fact["period_end"])

    loader_key = ["ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end"]
    sort_key = loader_key + ["_src", "accepted"]
    is_bs = fact["standard_concept"].isin(BS_CONCEPTS)
    if is_bs.any():
        bs = fact.loc[is_bs].copy()
        bs["absval"] = bs["value_as_filed"].abs()
        bs["_inst"] = bs["period_start"].isna().astype(int)
        bs = bs.sort_values(sort_key + ["_inst", "absval"], ascending=[True] * len(sort_key) + [False, False], kind="stable")
        bs = bs.drop_duplicates(subset=sort_key, keep="first").drop(columns=["absval", "_inst"])
        fact = pd.concat([fact.loc[~is_bs], bs], ignore_index=True)
    fact = fact.sort_values(sort_key, kind="stable").drop_duplicates(subset=loader_key, keep="first")
    flows = _build_pit_flows(fact)
    balance_sheets = _build_pit_bs(fact)
    max_accepted = accepted.max()
    status = f"local Valuein snapshot through {max_accepted.date()} ({len(fact):,} facts)"
    return flows, balance_sheets, status


def _build_pit_flows(fact: pd.DataFrame) -> dict:
    flows = fact.loc[fact.standard_concept.isin(FLOW_CONCEPTS), [
        "ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end", "accepted", "value_as_filed", "_src"
    ]].copy()
    if flows.empty:
        return {}
    flows = flows.sort_values(["ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end", "_src", "accepted"], kind="stable")
    direct = flows.loc[flows.fiscal_period.isin(["Q1", "Q2", "Q3", "Q4"]), [
        "ticker", "standard_concept", "period_end", "accepted", "value_as_filed", "_src"
    ]].rename(columns={"value_as_filed": "value"})
    fy_keys = ["ticker", "standard_concept", "fiscal_year"]
    annual = flows.loc[flows.fiscal_period == "FY"].drop_duplicates(fy_keys, keep="first")
    quarterly = flows.loc[flows.fiscal_period.isin(["Q1", "Q2", "Q3"])].drop_duplicates(fy_keys + ["fiscal_period"], keep="first")
    if not annual.empty:
        q = annual.merge(quarterly.pivot(index=fy_keys, columns="fiscal_period", values="value_as_filed").reset_index(), on=fy_keys, how="left")
        q1, q2, q3 = (q.get(name, pd.Series(np.nan, index=q.index)) for name in ("Q1", "Q2", "Q3"))
        has_direct_q4 = flows.loc[flows.fiscal_period == "Q4", fy_keys].drop_duplicates()
        q = q.merge(has_direct_q4.assign(_has_q4=True), on=fy_keys, how="left")
        use = q["_has_q4"].isna() & q1.notna() & q2.notna() & q3.notna()
        derived = q.loc[use, ["ticker", "standard_concept", "period_end", "accepted", "value_as_filed", "_src"]].copy()
        derived["value"] = derived.pop("value_as_filed") - q1.loc[use].to_numpy() - q2.loc[use].to_numpy() - q3.loc[use].to_numpy()
        direct = pd.concat([direct, derived], ignore_index=True)
    direct = direct.sort_values(["ticker", "standard_concept", "period_end", "_src", "accepted"], kind="stable")
    direct = direct.drop_duplicates(["ticker", "standard_concept", "period_end"], keep="first")
    direct = direct.sort_values(["ticker", "standard_concept", "period_end"]).reset_index(drop=True)
    return {(ticker, concept): group[["period_end", "accepted", "value"]].reset_index(drop=True)
            for (ticker, concept), group in direct.groupby(["ticker", "standard_concept"], sort=False)}


def _build_pit_bs(fact: pd.DataFrame) -> dict:
    out = {}
    bs = fact[fact.standard_concept.isin(BS_CONCEPTS)]
    for (ticker, concept), group in bs.groupby(["ticker", "standard_concept"], sort=False):
        frame = group[["period_end", "accepted", "_src", "period_start", "value_as_filed"]].rename(columns={"value_as_filed": "value"})
        frame["absval"] = frame["value"].abs()
        frame["_instant"] = frame["period_start"].isna().astype(int)
        frame = frame.sort_values(["period_end", "_src", "accepted", "_instant", "absval"], ascending=[True, True, True, False, False], kind="stable")
        frame = frame.drop_duplicates("period_end", keep="first").sort_values("period_end")
        out[(ticker, concept)] = frame[["period_end", "accepted", "value"]].reset_index(drop=True)
    return out


def _latest_asof(frame: pd.DataFrame | None, signal_date: pd.Timestamp) -> tuple[float, pd.Timestamp | None]:
    if frame is None or frame.empty:
        return np.nan, None
    available = frame.loc[frame["accepted"] <= signal_date]
    if available.empty:
        return np.nan, None
    row = available.iloc[-1]
    return float(row["value"]), pd.Timestamp(row["accepted"])


def _ttm_asof(frame: pd.DataFrame | None, signal_date: pd.Timestamp, max_span_days: int = 430) -> float:
    if frame is None or frame.empty:
        return np.nan
    available = frame.loc[frame["accepted"] <= signal_date].sort_values("period_end")
    if len(available) < 4:
        return np.nan
    last4 = available.tail(4)
    if int((last4.period_end.iloc[-1] - last4.period_end.iloc[0]).days) > max_span_days:
        return np.nan
    return float(last4.value.sum())


def _zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=1)
    if pd.isna(std) or std <= 0:
        return pd.Series(0.0, index=values.index)
    return (values - values.mean()) / std


def _passes_market_cap_guard(ticker: str, history: pd.Series, signal_date: pd.Timestamp, balance_sheets: dict) -> bool:
    price_now = float(history.iloc[-1])
    shares_now, accepted_now = _latest_asof(balance_sheets.get((ticker, "CommonSharesOutstanding")), signal_date)
    if not (price_now > 0 and pd.notna(shares_now) and shares_now > 0):
        return False
    market_cap = price_now * shares_now
    if not 1e6 <= market_cap <= 1e14:
        return False
    if len(history) < 22:
        return True
    price_ref = float(history.iloc[-22])
    ref_date = pd.Timestamp(history.index[-22])
    shares_ref, accepted_ref = _latest_asof(balance_sheets.get((ticker, "CommonSharesOutstanding")), ref_date)
    if not (price_ref > 0 and pd.notna(shares_ref) and shares_ref > 0):
        return False
    ratio = market_cap / (price_ref * shares_ref)
    if ticker in _COVERED_TICKERS:
        split_factor = 1.0
        if accepted_ref is not None and accepted_now is not None:
            for split_date, factor in _SPLIT_CAL.get(ticker, []):
                if accepted_ref < split_date <= accepted_now:
                    split_factor *= factor
        ratio /= split_factor
        return 1.0 / 2.5 <= ratio <= 2.5
    return 1.0 / 50.0 <= ratio <= 50.0


def _fundamental_scores(candidates: dict[str, pd.Series], signal_date: pd.Timestamp, flows: dict, balance_sheets: dict) -> pd.DataFrame:
    records = []
    for ticker, history in candidates.items():
        if not _passes_market_cap_guard(ticker, history, signal_date, balance_sheets):
            continue
        price_now = float(history.iloc[-1])
        shares, _ = _latest_asof(balance_sheets.get((ticker, "CommonSharesOutstanding")), signal_date)
        if not (pd.notna(shares) and shares > 0 and price_now > 0):
            continue
        market_cap = price_now * shares
        ni = _ttm_asof(flows.get((ticker, "NetIncome")), signal_date)
        revenue = _ttm_asof(flows.get((ticker, "TotalRevenue")), signal_date)
        gross_profit = _ttm_asof(flows.get((ticker, "GrossProfit")), signal_date)
        operating_cash = _ttm_asof(flows.get((ticker, "OperatingCashFlow")), signal_date)
        capex = _ttm_asof(flows.get((ticker, "CAPEX")), signal_date)
        equity, _ = _latest_asof(balance_sheets.get((ticker, "StockholdersEquity")), signal_date)
        assets, _ = _latest_asof(balance_sheets.get((ticker, "TotalAssets")), signal_date)
        short_debt, _ = _latest_asof(balance_sheets.get((ticker, "ShortTermDebt")), signal_date)
        long_debt, _ = _latest_asof(balance_sheets.get((ticker, "LongTermDebt")), signal_date)
        debt = np.nansum([short_debt, long_debt])
        fcf = operating_cash - capex if pd.notna(operating_cash) and pd.notna(capex) else np.nan
        records.append({
            "ticker": ticker,
            "ey": ni / market_cap if pd.notna(ni) else np.nan,
            "bp": equity / market_cap if pd.notna(equity) and equity > 0 else np.nan,
            "sy": revenue / market_cap if pd.notna(revenue) else np.nan,
            "fy": fcf / market_cap if pd.notna(fcf) else np.nan,
            "gpoa": gross_profit / assets if pd.notna(gross_profit) and pd.notna(assets) and assets > 0 else np.nan,
            "roe": ni / equity if pd.notna(ni) and pd.notna(equity) and equity > 0 else np.nan,
            "lev": -debt / equity if pd.notna(equity) and equity > 0 else np.nan,
            "accr": float(operating_cash > ni) if pd.notna(operating_cash) and pd.notna(ni) else np.nan,
        })
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records).set_index("ticker")
    value_columns = ["ey", "bp", "sy", "fy"]
    quality_columns = ["gpoa", "roe", "lev", "accr"]
    value_z = pd.DataFrame({column: _zscore(frame[column]).where(frame[column].notna()) for column in value_columns})
    quality_z = pd.DataFrame({column: _zscore(frame[column]).where(frame[column].notna()) for column in quality_columns})
    frame["VALUE"] = value_z.mean(axis=1, skipna=True)
    frame["QUALITY"] = quality_z.mean(axis=1, skipna=True)
    return frame.loc[value_z.notna().any(axis=1) & quality_z.notna().any(axis=1)]


def _momentum_13612(monthly: pd.DataFrame, ticker: str) -> float:
    if ticker not in monthly:
        return np.nan
    series = monthly[ticker].dropna()
    if len(series) < 13:
        return np.nan
    now = series.iloc[-1]
    return float(np.mean([now / series.iloc[-h - 1] - 1.0 for h in (1, 3, 6, 12)]))


def _trend(history: pd.Series) -> tuple[float, float]:
    monthly = history.resample("ME").last().dropna()
    price = float(history.iloc[-1])
    return price, float(monthly.tail(10).mean()) if len(monthly) >= 10 else np.nan


def _ordered_candidates(scores: pd.DataFrame) -> list[str]:
    if scores.empty:
        return []
    median = scores.QUALITY.median()
    pool = scores[scores.QUALITY >= median]
    if len(pool) < SELECT_K:
        pool = scores
    return pool.sort_values("VALUE", ascending=False).index.tolist()


def _update_held(scores: pd.DataFrame, trends: dict[str, tuple[float, float]], state: dict[str, list[str]]) -> list[str]:
    if scores.empty:
        return []
    q20 = scores.QUALITY.quantile(0.20)
    kept = []
    for ticker in state.get("held", []):
        if ticker in scores.index and ticker in trends:
            price, sma = trends[ticker]
            if pd.notna(sma) and price >= sma and scores.at[ticker, "QUALITY"] >= q20:
                kept.append(ticker)
    new = []
    for ticker in _ordered_candidates(scores):
        if ticker in kept or ticker not in trends:
            continue
        price, sma = trends[ticker]
        if pd.notna(sma) and price > 1.05 * sma:
            new.append(ticker)
    state["held"] = (kept + new)[:SELECT_K]
    return state["held"]


def _volatility_gate(spy: pd.Series, signal_date: pd.Timestamp) -> bool:
    returns = spy.loc[:signal_date].pct_change(fill_method=None).dropna()
    return True if len(returns) < 252 else float(returns.tail(20).std()) < float(returns.tail(252).std())


def val_monthly_targets(
    etf_prices: pd.DataFrame,
    constituent_prices: pd.DataFrame,
    flows: dict,
    balance_sheets: dict,
) -> pd.DataFrame:
    """Port of VAL: PIT quality/value selection, trend hysteresis, and defensive gate."""
    required = ("SPY", "TIP", *NDX_SAFE)
    missing = sorted(set(required) - set(etf_prices.columns))
    if missing:
        raise ValueError(f"Missing VAL gate/safe ETF prices: {', '.join(missing)}")
    import index_constitution as ic

    etf_prices = etf_prices.sort_index()
    constituent_prices = constituent_prices.sort_index()
    monthly = etf_prices.groupby(etf_prices.index.to_period("M")).tail(1)
    stock_monthly = constituent_prices.groupby(constituent_prices.index.to_period("M")).tail(1)
    combined = pd.concat([etf_prices, constituent_prices.reindex(etf_prices.index).ffill()], axis=1)
    combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]
    histories: list[tuple[pd.Timestamp, dict[str, float]]] = []
    state: dict[str, list[str]] = {"held": []}

    for signal_date in monthly.index:
        if signal_date < START_DATE or len(monthly.loc[:signal_date]) < 13:
            continue
        available = monthly.loc[:signal_date]
        safe_scores = {ticker: _momentum_13612(available, ticker) for ticker in NDX_SAFE}
        safe = max(NDX_SAFE, key=lambda ticker: safe_scores[ticker] if np.isfinite(safe_scores[ticker]) else -np.inf)
        gate_on = (
            _momentum_13612(available, "TIP") > 0
            and _momentum_13612(available, "SPY") > 0
            and _volatility_gate(etf_prices["SPY"], signal_date)
        )
        if not gate_on:
            histories.append((signal_date, {safe: 1.0}))
            continue

        try:
            pit = ic.constituents_at("nasdaq100", signal_date.strftime("%Y-%m-%d"))
            members = set(map(str, pit["symbol"].dropna().unique()))
        except Exception:
            members = set()
        if not members:
            histories.append((signal_date, {"SPY": 1.0}))
            continue

        candidates: dict[str, pd.Series] = {}
        trends: dict[str, tuple[float, float]] = {}
        for ticker in members.intersection(stock_monthly.columns):
            history = constituent_prices[ticker].loc[:signal_date].dropna()
            if len(history) < 260 or history.loc[signal_date - pd.Timedelta(days=30):signal_date].empty:
                continue
            candidates[ticker] = history
            trends[ticker] = _trend(history)
        scores = _fundamental_scores(candidates, signal_date, flows, balance_sheets)
        if scores.empty:
            histories.append((signal_date, {safe: 1.0}))
            continue
        selected = _update_held(scores, trends, state)
        weights = {ticker: 1.0 / SELECT_K for ticker in selected}
        residual = 1.0 - len(selected) / SELECT_K
        if residual > 1e-10:
            weights[safe] = weights.get(safe, 0.0) + residual
        histories.append((signal_date, weights))

    return _events_from_signals(combined, histories)
