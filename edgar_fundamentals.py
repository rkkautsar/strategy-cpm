"""DIY SEC-EDGAR fundamentals backfill (Phase 1: US us-gaap, USD reporters).

Pulls raw SEC EDGAR XBRL ``companyfacts`` for NASDAQ-100 historical tickers NOT
covered by the paid Valuein cache (delisted / acquired / foreign / non-S&P500
names) and emits Valuein-schema parquet so the VAL sleeve can consume them via
``data_loader.load_valuein_cache``.

Scope (Phase 1): emit facts ONLY for filers that report in **USD** AND use the
**us-gaap** taxonomy. Non-USD reporters (EUR/GBP/CNY/...) and ifrs-full filers
(e.g. AZN, ASML) are classified and recorded with a ``skip_reason`` but deferred
to Phase 2 (they need FX -> USD / IFRS normalization).

Deliverables (written by :func:`build_all`):
  1. ``data/edgar/cik_map.csv``           symbol,cik,taxonomy,currency,phase1_in,skip_reason
  2. ``data/valuein/fact_edgar.parquet``  same schema as fact.parquet (Phase-1 names only)
  3. ``data/valuein/security_edgar.parquet``  entity_id,symbol,is_primary_ticker,is_active,exchange

Entrypoint:
    python edgar_fundamentals.py --build          # (re)build 1-3 from the 143 list
    python edgar_fundamentals.py --build --refresh # force re-fetch companyfacts

Faithfulness validated by a prior spike (DIY-EDGAR reproduces Valuein @ 0.5% on
overlapping names); see /tmp/edgar_validate_REPORT.md. HTTP is read-only, sec.gov
+ data.sec.gov only, throttled <= ~7 req/s with a descriptive User-Agent.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EDGAR_DIR = DATA_DIR / "edgar"
VALUEIN_DIR = DATA_DIR / "valuein"
# Companyfacts JSON are large (~3MB each); cache outside the repo by default to
# avoid bloating data/. Override with EDGAR_CACHE_DIR.
CACHE_DIR = Path(os.environ.get("EDGAR_CACHE_DIR", "/tmp/edgar_cache"))

UNCOVERED_CSV = Path(os.environ.get("EDGAR_UNCOVERED_CSV", "/tmp/ndx_uncovered.csv"))

CIK_MAP_OUT = EDGAR_DIR / "cik_map.csv"
FACT_OUT = VALUEIN_DIR / "fact_edgar.parquet"
SEC_OUT = VALUEIN_DIR / "security_edgar.parquet"

UA = os.environ.get("EDGAR_UA", "strategy-cpm-fundamentals-backfill research@strategycpm.local")
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
BROWSE_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
              "&company={q}&type=10-K&dateb=&owner=include&count=10&output=atom")
REQ_SLEEP = 0.14  # ~7 req/s

# Valuein fact.parquet schema (column -> dtype) -- emitted facts MUST match.
FACT_COLUMNS = [
    "entity_id", "standard_concept", "numeric_value", "period_start", "period_end",
    "fiscal_year", "fiscal_period", "accepted_at", "value_current", "value_as_filed", "restated",
]
ACCEPTED_TZ = "Asia/Jakarta"  # matches existing Valuein accepted_at tz (date-only after loader strip)

# ---------------------------------------------------------------------------
# Tag mapping (validated; see /tmp/edgar_validate_REPORT.md). Priority order.
# ---------------------------------------------------------------------------
FLOW_TAGS = {
    "TotalRevenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ],
    "NetIncome": ["NetIncomeLoss"],
    "OperatingIncome": ["OperatingIncomeLoss"],
    "OperatingCashFlow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    # CAPEX: POSITIVE sign as stored by EDGAR (a payment); NO flip (matches Valuein).
    "CAPEX": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}
# GrossProfit handled specially (direct tag else Revenues - Cost).
GP_REV_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
GP_COST_TAGS = ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]

BS_TAGS = {
    "TotalAssets": ["Assets"],
    "TotalLiabilities": ["Liabilities"],
    "StockholdersEquity": ["StockholdersEquity"],
    "LongTermDebt": ["LongTermDebt"],            # TOTAL tag (incl current); NOT ...Noncurrent
    "ShortTermDebt": ["DebtCurrent", "LongTermDebtCurrent"],  # weak ~57%, accept gaps
}
SHARES_TAGS = [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]

# Value filters
MIN_ABS_VAL = 1.0          # drop |val| < 1 (rate/ratio pollution)
EQUITY_FLOOR = 1.0e6       # StockholdersEquity plausibility floor (~$1M)

# Duration span buckets (days)
Q_MIN, Q_MAX = 80, 100     # 3-month quarter (13-14 weeks)
FY_MIN, FY_MAX = 340, 380  # annual (52/53-week)

# ---------------------------------------------------------------------------
# Curated CIK overrides for delisted/acquired names absent from company_tickers
# (verified against data.sec.gov/submissions name + formerNames + tickers).
# ---------------------------------------------------------------------------
OVERRIDE_CIK = {
    "AEOS": 919012, "ALTR": 768251, "ALXN": 899866, "AMLN": 881464, "ANSS": 1013462,
    "APCC": 835910, "APOL": 929887, "ATVI": 718877, "BEAS": 1031798, "BMC": 835729,
    "BMET": 351346, "BRCM": 1054374, "CA": 356028, "CDWC": 899171, "CELG": 816284,
    "CEPH": 873364, "CERN": 804753, "CKFR": 949341, "CMCSK": 1166691, "CMVT": 803014,
    "CTRX": 1363851, "CTXS": 877890, "DISCA": 1437107, "DISCK": 1437107, "DISH": 1001082,
    "DTV": 1465112, "ENDP": 1593034, "ESRX": 1532063, "FLIR": 354908, "FMCN": 1330017,
    "FWLT": 1130385, "GENZ": 732485, "GMCR": 909954, "HOLX": 859737, "IACI": 891103,
    "JAVA": 709519, "JNPR": 1043604, "JOYG": 801898, "KRFT": 1545158, "LEAP": 1065049,
    "LLTC": 791907, "LVLT": 794323, "MEDI": 873591, "MXIM": 743316, "MYL": 1623613,
    "NDOI": 1100962, "NIHD": 1037016, "NLOK": 849399, "NLTI": 1270400, "NUAN": 1102556,
    "PDCO": 891024, "PETM": 863157, "PPDI": 1003124, "QRTEA": 1355096, "RIMM": 1070235,
    "SEPR": 877357, "SGEN": 1060736, "SHLD": 1310067, "SHPG": 936402, "SIAL": 90185,
    "SPLK": 1353283, "SPLS": 791519, "SRCL": 861878, "STRZA": 1507934, "TCFCA": 1308161,
    "TCFCB": 1308161, "TLAB": 317771, "UAUA": 100517, "VIAB": 813828, "VMED": 1270400,
    "WBA": 1618921, "WCRX": 1323854, "WFM": 865436, "WLTW": 1140536, "XLNX": 743988,
    "XMSR": 1091530, "YHOO": 1011006,
}
# Names with no reliable single US CIK (tangled tracking stocks / foreign IFRS).
DEFER_NO_CIK = {
    "LMCA": "liberty_tracking_ambiguous",
    "LMCK": "liberty_tracking_ambiguous",
    "VIP": "foreign_no_cik",  # VimpelCom/VEON -- foreign IFRS issuer
}


# ===========================================================================
# HTTP (read-only, throttled, cached)
# ===========================================================================
_last_req = [0.0]


def _throttle():
    dt = time.time() - _last_req[0]
    if dt < REQ_SLEEP:
        time.sleep(REQ_SLEEP - dt)
    _last_req[0] = time.time()


def _http_get(url: str, tries: int = 4) -> bytes | None:
    """GET with gzip + retry. Returns None on 404. Raises on persistent failure."""
    assert url.startswith(("https://www.sec.gov/", "https://data.sec.gov/")), f"non-SEC url: {url}"
    last = None
    for i in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            return raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
            time.sleep(0.7 * (i + 1))
        except Exception as e:  # noqa: BLE001 - network resilience
            last = e
            time.sleep(0.7 * (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url} ({last})")


def _cached_json(url: str, dest: Path) -> dict | None:
    if dest.exists():
        try:
            return json.loads(dest.read_text())
        except Exception:
            pass
    raw = _http_get(url)
    if raw is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return json.loads(raw)


def load_company_tickers() -> dict[str, int]:
    """ticker -> CIK (currently-listed filers only)."""
    j = _cached_json(COMPANY_TICKERS_URL, CACHE_DIR / "company_tickers.json")
    return {v["ticker"]: int(v["cik_str"]) for v in j.values()}


def fetch_companyfacts(cik: int, symbol: str = "") -> dict | None:
    dest = CACHE_DIR / f"companyfacts_{symbol or 'X'}_{cik:010d}.json"
    return _cached_json(COMPANYFACTS_URL.format(cik=cik), dest)


def _toks(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]", " ", s.lower()).split())


def browse_edgar_cik(name: str, expected_symbol: str) -> int | None:
    """Fallback CIK resolution via browse-edgar atom + submissions name verification."""
    words = re.sub(r"[^A-Za-z0-9 ]", " ", name).split()
    queries = [name]
    if len(words) >= 2:
        queries.append(" ".join(words[:2]))
    if words:
        queries.append(words[0])
    cand: list[str] = []
    for q in queries:
        raw = _http_get(BROWSE_URL.format(q=urllib.parse.quote(q)))
        if raw:
            for c in re.findall(r"<cik>(\d+)</cik>", raw.decode("utf-8", "replace")):
                if c not in cand:
                    cand.append(c)
        if cand:
            break
    name_tok = _toks(name)
    best, best_score = None, -1.0
    for c in cand[:6]:
        sub = _cached_json(SUBMISSIONS_URL.format(cik=int(c)), CACHE_DIR / f"submissions_{int(c):010d}.json")
        if not sub:
            continue
        names = [sub.get("name", "")] + [f.get("name", "") for f in sub.get("formerNames", [])]
        if expected_symbol in (sub.get("tickers") or []):
            return int(c)
        score = max((len(name_tok & _toks(n)) / max(1, len(name_tok)) for n in names), default=0.0)
        if score > best_score:
            best, best_score = int(c), score
    return best if best_score >= 0.5 else None


def resolve_cik(symbol: str, name: str, sym2cik: dict[str, int]) -> tuple[int | None, str]:
    """Return (cik, method). method in {override, company_tickers, browse_edgar, unresolved}."""
    if symbol in OVERRIDE_CIK:
        return OVERRIDE_CIK[symbol], "override"
    if symbol in sym2cik:
        return sym2cik[symbol], "company_tickers"
    cik = browse_edgar_cik(name, symbol)
    if cik is not None:
        return cik, "browse_edgar"
    return None, "unresolved"


# ===========================================================================
# Classification (taxonomy + reporting currency)
# ===========================================================================
_CCY_RE = re.compile(r"[A-Z]{3}")
_CCY_PROBE_TAGS = (
    "Assets", "Liabilities", "Revenues", "StockholdersEquity", "NetIncomeLoss",
    "EquityAttributableToOwnersOfParent", "RevenueFromContractsWithCustomers",
)


def _node_currency(node: dict) -> str | None:
    """MAJORITY currency by fact-entry count among core financials within one
    taxonomy node. A CNY-functional ADR with only sparse USD *convenience*
    translations resolves to CNY (deferred), not USD; tie-break prefers USD.
    """
    from collections import Counter

    cnt: Counter = Counter()
    for tag in _CCY_PROBE_TAGS:
        t = node.get(tag)
        if not t:
            continue
        for unit, entries in t.get("units", {}).items():
            if _CCY_RE.fullmatch(unit):
                cnt[unit] += len(entries)
    if not cnt:
        return None
    top = max(cnt.values())
    leaders = [u for u, n in cnt.items() if n == top]
    return "USD" if "USD" in leaders else sorted(leaders)[0]


def _core_count(node: dict) -> int:
    return sum(1 for t in _CCY_PROBE_TAGS if node.get(t))


def classify(companyfacts: dict) -> tuple[str, str, bool, str]:
    """(taxonomy, currency, phase1_in, skip_reason).

    Primary taxonomy = the one that actually carries the core financials (some
    foreign IFRS filers also expose a token us-gaap concept; financials live in
    ifrs-full). phase1_in requires primary=us-gaap AND majority currency USD.
    """
    facts = companyfacts.get("facts", {})
    us = facts.get("us-gaap") or {}
    ifrs = facts.get("ifrs-full") or {}
    if not us and not ifrs:
        return "none", "", False, "no_fundamental_taxonomy"

    us_core, ifrs_core = _core_count(us), _core_count(ifrs)
    if us_core or ifrs_core:
        primary = "us-gaap" if us_core >= ifrs_core else "ifrs-full"
    else:  # neither has core probe tags -> larger taxonomy by tag count
        primary = "us-gaap" if (us and len(us) >= len(ifrs)) else ("ifrs-full" if ifrs else "us-gaap")
    node = us if primary == "us-gaap" else ifrs
    cur = _node_currency(node)

    if primary == "ifrs-full":
        return "ifrs-full", (cur or "unknown"), False, "ifrs_taxonomy"
    if cur == "USD":
        return "us-gaap", "USD", True, ""
    return "us-gaap", (cur or "unknown"), False, f"non_usd_{cur or 'unknown'}"


# ===========================================================================
# Fact extraction
# ===========================================================================
def _iter_dur(node: dict):
    """Yield (start, end, span_days, fp, fy, filed, val) for USD duration entries."""
    for e in node.get("units", {}).get("USD", []):
        if "start" not in e or "end" not in e:
            continue
        if e.get("val") is None or e.get("filed") is None or e.get("fp") is None:
            continue
        s = pd.Timestamp(e["start"])
        en = pd.Timestamp(e["end"])
        yield s, en, (en - s).days, e["fp"], e.get("fy"), e["filed"], float(e["val"])


def _bucket_fp(span: int, fp: str) -> str | None:
    if Q_MIN <= span <= Q_MAX and fp in ("Q1", "Q2", "Q3"):
        return fp
    if FY_MIN <= span <= FY_MAX and fp == "FY":
        return "FY"
    return None


def _flow_rows_multi(facts: dict, concept: str, tags: list[str]) -> list[tuple]:
    """Stitch alternative tags across accounting eras (e.g. SalesRevenueNet ->
    RevenueFromContractWithCustomerExcludingAssessedTax at ASC 606). Per
    (period_end, fp) keep the value from the HIGHEST-priority tag present;
    within a tag keep the earliest filing (as-filed). Priority order matches the
    validated single-tag choice where eras overlap.
    """
    by_period: dict = {}
    for tag in tags:  # priority order
        node = facts.get("us-gaap", {}).get(tag)
        if not node or not node.get("units", {}).get("USD"):
            continue
        local: dict = {}
        for s, en, span, fp, fy, filed, val in _iter_dur(node):
            ofp = _bucket_fp(span, fp)
            if ofp is None:
                continue
            k = (en, ofp)
            f = pd.Timestamp(filed)
            if k not in local or f < local[k][5]:
                local[k] = (concept, en, s, fy, ofp, f, val)
        for k, row in local.items():
            by_period.setdefault(k, row)  # higher-priority tag wins
    return list(by_period.values())


def _dur_map(node: dict) -> dict:
    """(start, end) -> (fp, fy, filed, val) keeping earliest-filed."""
    out: dict = {}
    for s, en, span, fp, fy, filed, val in _iter_dur(node):
        k = (s, en)
        if k not in out or filed < out[k][2]:
            out[k] = (fp, fy, filed, val)
    return out


def _first_node(facts: dict, tags: list[str], tax: str = "us-gaap") -> dict | None:
    for tag in tags:
        node = facts.get(tax, {}).get(tag)
        if node and node.get("units", {}).get("USD"):
            return node
    return None


def _gross_profit_rows(facts: dict) -> list[tuple]:
    node = facts.get("us-gaap", {}).get("GrossProfit")
    if node and node.get("units", {}).get("USD"):
        return _flow_rows_multi(facts, "GrossProfit", ["GrossProfit"])
    rev_node = _first_node(facts, GP_REV_TAGS)
    cost_node = _first_node(facts, GP_COST_TAGS)
    if not rev_node or not cost_node:
        return []
    rev, cost = _dur_map(rev_node), _dur_map(cost_node)
    rows = []
    for (s, en), (fp, fy, rfiled, rval) in rev.items():
        if (s, en) not in cost:
            continue
        cfp, cfy, cfiled, cval = cost[(s, en)]
        ofp = _bucket_fp((en - s).days, fp)
        if ofp is None:
            continue
        rows.append(("GrossProfit", en, s, fy, ofp, max(rfiled, cfiled), float(rval - cval)))
    return rows


def _bs_rows_multi(facts: dict, concept: str, tags: list[str]) -> list[tuple]:
    """Instant (balance-sheet) facts, priority-stitched across tags per
    (period_end, fp). E.g. ShortTermDebt: DebtCurrent before LongTermDebtCurrent.
    """
    by_period: dict = {}
    for tag in tags:  # priority order
        node = facts.get("us-gaap", {}).get(tag)
        if not node or not node.get("units", {}).get("USD"):
            continue
        local: dict = {}
        for e in node["units"]["USD"]:
            if "start" in e:  # instant only
                continue
            end, fp, fy, val, filed = e.get("end"), e.get("fp"), e.get("fy"), e.get("val"), e.get("filed")
            if None in (end, fp, val, filed) or fp not in ("Q1", "Q2", "Q3", "FY"):
                continue
            k = (pd.Timestamp(end), fp)
            f = pd.Timestamp(filed)
            if k not in local or f < local[k][5]:
                local[k] = (concept, pd.Timestamp(end), pd.NaT, fy, fp, f, float(val))
        for k, row in local.items():
            by_period.setdefault(k, row)
    return list(by_period.values())


def _shares_rows(facts: dict) -> list[tuple]:
    for tax, tag in SHARES_TAGS:
        node = facts.get(tax, {}).get(tag)
        if not node:
            continue
        entries = node.get("units", {}).get("shares", [])
        if not entries:
            continue
        rows = []
        for e in entries:
            if "start" in e:
                continue
            end, fp, fy, val, filed = e.get("end"), e.get("fp"), e.get("fy"), e.get("val"), e.get("filed")
            if None in (end, fp, val, filed) or fp not in ("Q1", "Q2", "Q3", "FY"):
                continue
            rows.append(("CommonSharesOutstanding", pd.Timestamp(end), pd.NaT, fy, fp, filed, float(val)))
        if rows:
            return rows
    return []


_SHARE_SCALES = (1e-6, 1e-3, 1e3, 1e6)


def _shares_scale_guard(df: pd.DataFrame) -> pd.DataFrame:
    """Fix rare share-count unit/filer errors (two-sided, multi-scale).

    A within-ticker share value off the series median by >100x is almost always
    a unit error (thousands, or a ~1e6 filer typo e.g. FOSL 5.29e13 vs ~52.9M),
    never a real change. Rescale by the power of 1000 that lands within 10x of
    the median; leave untouched if no scale fits.
    """
    m = df["standard_concept"] == "CommonSharesOutstanding"
    if m.sum() < 3:
        return df
    med = df.loc[m, "value"].median()
    if not (med and med > 0):
        return df
    for idx, v in df.loc[m, "value"].items():
        if not (v and v > 0):
            continue
        ratio = v / med
        if 0.01 <= ratio <= 100:
            continue
        best = None
        for s in _SHARE_SCALES:
            c = v * s
            if med / 10.0 <= c <= med * 10.0 and (best is None or abs(c - med) < abs(best - med)):
                best = c
        if best is not None:
            df.loc[idx, "value"] = best
    return df


def extract_facts(companyfacts: dict, cik: int) -> pd.DataFrame:
    """Emit Valuein-schema facts for one filer (Phase-1 us-gaap USD assumed)."""
    facts = companyfacts.get("facts", {})
    raw: list[tuple] = []
    for concept, tags in FLOW_TAGS.items():
        raw.extend(_flow_rows_multi(facts, concept, tags))
    raw.extend(_gross_profit_rows(facts))
    for concept, tags in BS_TAGS.items():
        raw.extend(_bs_rows_multi(facts, concept, tags))
    raw.extend(_shares_rows(facts))

    if not raw:
        return pd.DataFrame(columns=FACT_COLUMNS)

    df = pd.DataFrame(raw, columns=["standard_concept", "period_end", "period_start",
                                    "fiscal_year", "fiscal_period", "filed", "value"])
    # As-filed: keep earliest filing per (concept, period_end, fiscal_period).
    df["filed"] = pd.to_datetime(df["filed"])
    df = df.sort_values("filed").drop_duplicates(
        subset=["standard_concept", "period_end", "fiscal_period"], keep="first")

    # Value-faithfulness filters.
    df = df[df["value"].abs() >= MIN_ABS_VAL]
    eq = df["standard_concept"] == "StockholdersEquity"
    df = df[~(eq & (df["value"].abs() < EQUITY_FLOOR))]
    df = _shares_scale_guard(df)
    df = df[df["value"].notna()]
    if df.empty:
        return pd.DataFrame(columns=FACT_COLUMNS)

    # fiscal_year: fill missing from period_end year.
    fy = pd.to_numeric(df["fiscal_year"], errors="coerce")
    df["fiscal_year"] = fy.fillna(pd.to_datetime(df["period_end"]).dt.year).astype("int64")

    out = pd.DataFrame({
        "entity_id": f"{cik:010d}",
        "standard_concept": df["standard_concept"].astype(str),
        "numeric_value": df["value"].astype("float64"),
        "period_start": pd.to_datetime(df["period_start"]).astype("datetime64[us]"),
        "period_end": pd.to_datetime(df["period_end"]).astype("datetime64[us]"),
        "fiscal_year": df["fiscal_year"].astype("int64"),
        "fiscal_period": df["fiscal_period"].astype(str),
        "accepted_at": df["filed"].dt.tz_localize(ACCEPTED_TZ).astype(f"datetime64[us, {ACCEPTED_TZ}]"),
        "value_current": df["value"].astype("float64"),
        "value_as_filed": df["value"].astype("float64"),
        "restated": False,
    })
    return out[FACT_COLUMNS].reset_index(drop=True)


# ===========================================================================
# Build orchestration
# ===========================================================================
def _load_uncovered() -> pd.DataFrame:
    """143 uncovered symbols with NDX membership tenure (for dup tie-break)."""
    if UNCOVERED_CSV.exists():
        u = pd.read_csv(UNCOVERED_CSV)
    else:
        import index_constitution as ic
        hist = ic.history("nasdaq100")
        sec = pd.read_parquet(VALUEIN_DIR / "security.parquet")
        covered = set(sec[sec.is_primary_ticker].symbol)
        syms = sorted(set(hist.symbol) - covered)
        u = hist[hist.symbol.isin(syms)][["symbol", "name"]].drop_duplicates("symbol")
        u["opt-in"], u["opt-out"] = pd.NaT, pd.NaT
    u = u.rename(columns={"name": "cname"})
    u["opt_in"] = pd.to_datetime(u.get("opt-in"), errors="coerce")
    u["opt_out"] = pd.to_datetime(u.get("opt-out"), errors="coerce")
    agg = (u.groupby("symbol")
             .agg(cname=("cname", "first"), opt_in=("opt_in", "min"), opt_out=("opt_out", "max"))
             .reset_index())
    end = agg["opt_out"].fillna(pd.Timestamp.today())
    agg["tenure_days"] = (end - agg["opt_in"]).dt.days.fillna(0)
    return agg


def build_all(refresh: bool = False) -> dict:
    """Resolve CIKs, classify, emit cik_map.csv + fact_edgar/security_edgar parquet."""
    EDGAR_DIR.mkdir(parents=True, exist_ok=True)
    VALUEIN_DIR.mkdir(parents=True, exist_ok=True)
    if refresh:
        for p in CACHE_DIR.glob("companyfacts_*.json"):
            p.unlink()

    sym2cik = load_company_tickers()
    live_syms = set(sym2cik)
    uncovered = _load_uncovered()
    valuein_eids = set(pd.read_parquet(VALUEIN_DIR / "security.parquet").entity_id.astype(str))

    # --- Pass 1: resolve CIKs --------------------------------------------------
    rows = []  # symbol, cname, cik, method, tenure_days
    for r in uncovered.itertuples():
        if r.symbol in DEFER_NO_CIK:
            rows.append((r.symbol, r.cname, None, "deferred", r.tenure_days))
            continue
        cik, method = resolve_cik(r.symbol, str(r.cname), sym2cik)
        rows.append((r.symbol, r.cname, cik, method, r.tenure_days))
    res = pd.DataFrame(rows, columns=["symbol", "cname", "cik", "method", "tenure_days"])

    # --- Pass 2: collision resolution -----------------------------------------
    # Intra-EDGAR: many uncovered tickers share one CIK (share classes / renames).
    # Pick one primary per CIK (longest NDX tenure, tie alpha); others -> dup.
    primary_of: dict[int, str] = {}
    for cik, g in res[res.cik.notna()].groupby("cik"):
        g = g.sort_values(["tenure_days", "symbol"], ascending=[False, True])
        primary_of[int(cik)] = g.iloc[0].symbol

    cik_map_rows = []
    emit_targets = []  # (symbol, cik)
    for r in res.itertuples():
        sym, cik = r.symbol, r.cik
        if cik is None or pd.isna(cik):
            reason = DEFER_NO_CIK.get(sym, "cik_unresolved")
            cik_map_rows.append(dict(symbol=sym, cik="", taxonomy="", currency="",
                                     phase1_in=False, skip_reason=reason))
            continue
        cik = int(cik)
        eid = f"{cik:010d}"
        if eid in valuein_eids:
            cik_map_rows.append(dict(symbol=sym, cik=cik, taxonomy="(in_valuein)", currency="",
                                     phase1_in=False, skip_reason="cik_in_valuein"))
            continue
        if primary_of.get(cik) != sym:
            cik_map_rows.append(dict(symbol=sym, cik=cik, taxonomy="", currency="",
                                     phase1_in=False, skip_reason=f"cik_dup_of:{primary_of.get(cik)}"))
            continue
        emit_targets.append((sym, cik))

    # --- Pass 3: fetch, classify, extract -------------------------------------
    fact_frames = []
    sec_rows = []
    for sym, cik in emit_targets:
        cf = fetch_companyfacts(cik, sym)
        if cf is None:
            cik_map_rows.append(dict(symbol=sym, cik=cik, taxonomy="", currency="",
                                     phase1_in=False, skip_reason="no_companyfacts"))
            continue
        taxonomy, currency, phase1_in, skip = classify(cf)
        if not phase1_in:
            cik_map_rows.append(dict(symbol=sym, cik=cik, taxonomy=taxonomy, currency=currency,
                                     phase1_in=False, skip_reason=skip))
            continue
        facts = extract_facts(cf, cik)
        if facts.empty:
            cik_map_rows.append(dict(symbol=sym, cik=cik, taxonomy=taxonomy, currency=currency,
                                     phase1_in=False, skip_reason="no_facts_extracted"))
            continue
        fact_frames.append(facts)
        sec_rows.append(dict(entity_id=f"{cik:010d}", symbol=sym, is_primary_ticker=True,
                             is_active=(sym in live_syms), exchange="NASDAQ"))
        cik_map_rows.append(dict(symbol=sym, cik=cik, taxonomy=taxonomy, currency=currency,
                                 phase1_in=True, skip_reason=""))
        print(f"  emit {sym:7s} cik={cik:<8d} facts={len(facts):4d}", file=sys.stderr)

    # --- Write deliverables ----------------------------------------------------
    cik_map = pd.DataFrame(cik_map_rows).sort_values("symbol")
    cik_map.to_csv(CIK_MAP_OUT, index=False, quoting=csv.QUOTE_MINIMAL)

    if fact_frames:
        fact_edgar = pd.concat(fact_frames, ignore_index=True)
    else:
        fact_edgar = pd.DataFrame(columns=FACT_COLUMNS)
    fact_edgar.to_parquet(FACT_OUT, index=False)

    sec_edgar = pd.DataFrame(sec_rows, columns=["entity_id", "symbol", "is_primary_ticker",
                                                "is_active", "exchange"])
    sec_edgar.to_parquet(SEC_OUT, index=False)

    summary = {
        "phase1_in": int((cik_map.phase1_in == True).sum()),  # noqa: E712
        "deferred_foreign_ifrs": int(cik_map.skip_reason.str.startswith(("non_usd", "ifrs")).sum()),
        "cik_in_valuein": int((cik_map.skip_reason == "cik_in_valuein").sum()),
        "cik_dup": int(cik_map.skip_reason.str.startswith("cik_dup_of").sum()),
        "unresolved_or_deferred_no_cik": int(cik_map.skip_reason.isin(
            list(set(DEFER_NO_CIK.values())) + ["cik_unresolved"]).sum()),
        "browse_edgar_resolved": int((res.method == "browse_edgar").sum()),
        "n_facts": int(len(fact_edgar)),
        "n_securities": int(len(sec_edgar)),
        "files": {"cik_map": str(CIK_MAP_OUT), "fact": str(FACT_OUT), "security": str(SEC_OUT)},
    }
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="(re)build cik_map + fact/security parquet")
    ap.add_argument("--refresh", action="store_true", help="force re-fetch companyfacts JSON")
    args = ap.parse_args()
    if not args.build:
        ap.print_help()
        return
    summary = build_all(refresh=args.refresh)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
