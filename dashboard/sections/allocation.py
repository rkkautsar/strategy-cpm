from __future__ import annotations
import pandas as pd
import numpy as np
from types import SimpleNamespace
from config import CPM_WEIGHT as CPM_W, NDX_WEIGHT as NDX_W, VAL_WEIGHT as VAL_W, RPV_WEIGHT as RPV_W
from cpm_live import DEFAULT_CASH, SAFE_POOL
from dashboard_engine import cpm_signal_records, CASH_TICKER
from rpv_live import compute_rpv_weights
from core import cached_value_backtest

# Production blend weights
CPM_WEIGHT = CPM_W
NDX_WEIGHT = NDX_W
VAL_WEIGHT = VAL_W
RPV_WEIGHT = RPV_W

NDX_SECTORS = {
    # Semis
    "NVDA":"Semis", "AVGO":"Semis", "AMD":"Semis", "INTC":"Semis",
    "QCOM":"Semis", "AMAT":"Semis", "MU":"Semis", "LRCX":"Semis",
    "KLAC":"Semis", "MCHP":"Semis", "MRVL":"Semis", "NXPI":"Semis",
    "ASML":"Semis", "ARM":"Semis", "ADI":"Semis", "ON":"Semis",
    "TXN":"Semis",
    # Mega-cap software / platforms
    "MSFT":"Software", "GOOGL":"Internet", "GOOG":"Internet",
    "META":"Internet", "AAPL":"Hardware/Software", "AMZN":"Internet/Retail",
    "NFLX":"Streaming", "ADBE":"Software", "CRM":"Software",
    "INTU":"Software", "ORCL":"Software", "NOW":"Software",
    "SNPS":"Software/EDA", "CDNS":"Software/EDA", "WDAY":"Software",
    "CTSH":"Software", "FTNT":"Cybersec", "PANW":"Cybersec",
    "CRWD":"Cybersec", "ZS":"Cybersec", "CSCO":"Networking",
    # Storage / hardware
    "WDC":"Storage", "STX":"Storage", "SNDK":"Storage",
    # Consumer
    "TSLA":"Auto/EV", "COST":"Retail", "PEP":"Consumer Staples",
    "MDLZ":"Consumer Staples", "MAR":"Hospitality", "BKNG":"Travel",
    "ABNB":"Travel", "DASH":"Internet", "LULU":"Apparel",
    "SBUX":"Restaurants", "MNST":"Beverages", "KDP":"Beverages",
    # Healthcare/biotech
    "AMGN":"Biotech", "GILD":"Biotech", "VRTX":"Biotech",
    "REGN":"Biotech", "ISRG":"MedTech", "DXCM":"MedTech",
    "IDXX":"MedTech", "MRNA":"Biotech", "BIIB":"Biotech",
    # Other
    "TMUS":"Telecom", "CMCSA":"Media/Cable", "CHTR":"Media/Cable",
    "PYPL":"Fintech", "PDD":"Internet/Retail", "MELI":"Internet/Retail",
    "PCAR":"Trucks", "FAST":"Industrials", "CSX":"Rail",
    "ODFL":"Trucks", "EXC":"Utilities", "AEP":"Utilities",
    "XEL":"Utilities", "CTAS":"Services", "ROST":"Retail",
    "ORLY":"Auto Parts", "AZN":"Pharma",
    # Current NDX-100 additions (2026-05)
    "ADP":"Services", "PAYX":"Services",
    "ADSK":"Software", "EA":"Gaming", "TTWO":"Gaming",
    "DDOG":"Software", "PLTR":"Software", "SHOP":"Internet/Retail",
    "APP":"AdTech", "MSTR":"Software", "CSGP":"Data/RE",
    "VRSK":"Data/Analytics", "TRI":"Media/Data",
    "ALNY":"Biotech", "INSM":"Biotech", "ENDP":"Pharma",
    "GEHC":"MedTech",
    "MPWR":"Semis",
    "AXON":"Defense", "HON":"Industrials", "ROP":"Industrials",
    "CPRT":"Auto Services", "FER":"Auto",
    "BKR":"Energy", "FANG":"Energy", "CEG":"Utilities",
    "LIN":"Materials",
    "CCEP":"Beverages", "KHC":"Consumer Staples", "WMT":"Retail",
    "WBD":"Media", "NWSA":"Media", "WLTW":"Insurance/Consulting",
}

def _ndx_sector_summary(picks: list) -> str:
    if not picks:
        return "(no active picks)"
    counts = {}
    for t in picks:
        s = NDX_SECTORS.get(t, "Unknown/?")
        counts[s] = counts.get(s, 0) + 1
    parts = [f"{c} {s}" for s, c in sorted(counts.items(), key=lambda x: -x[1])]
    return " | ".join(parts)

def current_alloc_html(panel: pd.DataFrame, sig_d: pd.Timestamp,
                         rpv_spy_rets: pd.Series | None = None,
                         ndx_rets: pd.Series | None = None,
                         art = None) -> str:
    # Pull current allocation from precomputed records (no recomputation).
    if art is not None:
        records = [r for r in art.cpm_records if r["sig_d"] <= sig_d]
        rpv_records_subset = [r for r in art.rpv_records if r["sig_d"] <= sig_d]
        ndx_records_subset = [r for r in art.ndx_records if r["sig_d"] <= sig_d] if art.ndx_records else []
        val_records_subset = [r for r in art.val_records if r["sig_d"] <= sig_d] if getattr(art, "val_records", None) else []
        cpm_rec = records[-1] if records else {"weights": {}, "basket": None, "regime": "DEFENSIVE", "safe": DEFAULT_CASH}
        rpv_rec = rpv_records_subset[-1] if rpv_records_subset else {"weights": {}, "regime": "CASH", "diag": {}}
        ndx_rec = ndx_records_subset[-1] if ndx_records_subset else None
        val_rec = val_records_subset[-1] if val_records_subset else None
    else:
        # Fallback when art is not provided.
        records = cpm_signal_records(panel, pd.Timestamp("1900-01-01"), sig_d)
        cpm_rec = records[-1] if records else {"weights": {}, "basket": None, "regime": "DEFENSIVE", "safe": DEFAULT_CASH}
        rpv_rec = ndx_rec = val_rec = None
    weights = cpm_rec["weights"]
    regime = cpm_rec["regime"]
    safe = cpm_rec["safe"]

    # Cross-asset Parity Momentum (CPM) sleeve (60%)
    fcp_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(weights.items(), key=lambda x: -x[1]))
    risky_basket = [t for t, w in sorted(weights.items(), key=lambda x: -x[1]) if t != safe and w > 0]
    basket_str = " + ".join(risky_basket) if risky_basket else "-"

    # RPV sleeve (10%) -- from precomputed record if available
    if rpv_rec is not None:
        bq_w, bq_regime, bq_diag = rpv_rec["weights"], rpv_rec["regime"], rpv_rec["diag"]
    else:
        bq_w, bq_regime, bq_diag = compute_rpv_weights(panel, sig_d)
    bq_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(bq_w.items(), key=lambda x: -x[1]))
    if bq_regime != "CASH":
        bq_state = f"{bq_regime}"
    else:
        bq_state = f"CASH ({bq_diag.get('reason','-')})"

    # NDX sleeve (15%) -- TIP canary + SPY trend + SPY RV20<RV252 gate
    ndx_panel_data = None
    try:
        from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel, SELECT_K as NDX_SELECT_K
        if ndx_rec is not None:
            ndx_w, ndx_regime, ndx_diag = ndx_rec["weights"], ndx_rec["regime"], ndx_rec["diag"]
        else:
            ndx_panel_data = load_ndx_panel()
            ndx_w, ndx_regime, ndx_diag = compute_ndx_weights(panel, ndx_panel_data, sig_d)
        ndx_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                            for t, w in sorted(ndx_w.items(), key=lambda x: -x[1]))
        if ndx_regime == "NDX_ACTIVE" or ndx_regime.startswith("NDX_PARTIAL"):
            sel = ndx_diag.get('selected', [])
            sector_summary = _ndx_sector_summary(sel)
            mode = f"{ndx_regime} | top-{NDX_SELECT_K} raw 13612U momentum"
            ndx_state = (f"{mode}: {', '.join(sel)}<br>Sector mix: {sector_summary}")
        else:
            ndx_state = f"{ndx_regime} -- {ndx_diag.get('reason', '100% cash')}"
    except (FileNotFoundError, ImportError) as e:
        ndx_w = {CASH_TICKER: 1.0}
        ndx_html = "<tr><td colspan='2'>(NDX panel not available)</td></tr>"
        ndx_state = f"NDX panel data unavailable ({e})"

    # VAL sleeve (15%) -- stateful he5_te0 trend band, derived from full-history run.
    if val_rec is not None:
        val_w = val_rec.get("weights", {CASH_TICKER: 1.0})
        val_regime = val_rec.get("regime", "VAL_UNKNOWN")
        val_selected = val_rec.get("selected", [])
    else:
        if ndx_panel_data is None:
            try:
                from ndx_sleeve_live import load_ndx_panel
                ndx_panel_data = load_ndx_panel()
            except (FileNotFoundError, ImportError):
                ndx_panel_data = None
        if ndx_panel_data is None:
            val_w = {CASH_TICKER: 1.0}
            val_regime = "VAL_DATA_UNAVAILABLE"
            val_selected = []
        else:
            val_start = max(pd.Timestamp("2010-06-01"), panel.index.min())
            _, val_hist = cached_value_backtest(panel, ndx_panel_data, val_start, sig_d)
            live_val = next((r for r in reversed(val_hist) if r["sig_d"] <= sig_d), None)
            if live_val is None:
                val_w = {CASH_TICKER: 1.0}
                val_regime = "VAL_NO_SIGNAL"
                val_selected = []
            else:
                val_w = live_val.get("weights", {CASH_TICKER: 1.0})
                val_regime = live_val.get("regime", "VAL_UNKNOWN")
                val_selected = live_val.get("selected", [])
    val_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                         for t, w in sorted(val_w.items(), key=lambda x: -x[1]))
    val_state = f"{val_regime} -- picks: {', '.join(val_selected) if val_selected else '(none)'}"

    # Combined 60% CPM + 15% NDX + 15% VAL + 10% RPV (UNSCALED)
    combined_uncapped = {}
    for t, w in weights.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * CPM_WEIGHT
    for t, w in ndx_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * NDX_WEIGHT
    for t, w in val_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * VAL_WEIGHT
    for t, w in bq_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * RPV_WEIGHT

    # Combined target weights (no extra portfolio cap overlay)
    combined = combined_uncapped
    combined_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                             for t, w in sorted(combined.items(), key=lambda x: -x[1])
                             if abs(w) > 1e-6)

    # Monthly sleeve gates only.
    dd_status_html = (
        "<div style='grid-column: 1 / -1; background:#fafafa;border-left:4px solid #3498db;"
        "padding:8px 12px;margin:8px 0;border-radius:4px;font-size:0.88rem;'>"
        "<strong>NDX + VAL gate model</strong>: monthly TIP canary + SPY trend + SPY RV20&lt;RV252. "
        "When any gate leg fails, that sleeve allocates 100% best-of-safe (SHV/IEF)."
        "</div>"
    )

    # Build previous-vs-target trade-delta table (compare to PREVIOUS signal date if available)
    prev_combined = {}
    if len(records) >= 2:
        prev_rec = records[-2]
        prev_weights = prev_rec.get("weights", {})
        try:
            prev_sd = prev_rec.get("sig_d", None)
            # Prefer precomputed rpv/ndx/val records (no recomputation)
            if art is not None and prev_sd is not None:
                prev_rpv_rec = next((r for r in reversed(art.rpv_records) if r["sig_d"] == prev_sd), None)
                prev_ndx_rec = next((r for r in reversed(art.ndx_records) if r["sig_d"] == prev_sd), None) if art.ndx_records else None
                prev_val_rec = next((r for r in reversed(art.val_records) if r["sig_d"] == prev_sd), None) if getattr(art, "val_records", None) else None
                prev_bq_w = prev_rpv_rec["weights"] if prev_rpv_rec else {}
                prev_ndx_w = prev_ndx_rec["weights"] if prev_ndx_rec else {}
                prev_val_w = prev_val_rec["weights"] if prev_val_rec else {}
            else:
                prev_bq_w, _, _ = compute_rpv_weights(panel, prev_sd) if prev_sd is not None else ({}, None, {})
                prev_ndx_w, _, _ = compute_ndx_weights(panel, ndx_panel_data, prev_sd) if prev_sd is not None else ({}, None, {})
                if prev_sd is not None and ndx_panel_data is not None:
                    val_start = max(pd.Timestamp("2010-06-01"), panel.index.min())
                    _, prev_val_hist = cached_value_backtest(panel, ndx_panel_data, val_start, prev_sd)
                    prev_val_live = next((r for r in reversed(prev_val_hist) if r["sig_d"] <= prev_sd), None)
                    prev_val_w = prev_val_live.get("weights", {}) if prev_val_live else {}
                else:
                    prev_val_w = {}
        except Exception:
            prev_bq_w, prev_ndx_w, prev_val_w = {}, {}, {}
        for t, w in prev_weights.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * CPM_WEIGHT
        for t, w in prev_ndx_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * NDX_WEIGHT
        for t, w in prev_val_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * VAL_WEIGHT
        for t, w in prev_bq_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * RPV_WEIGHT
    all_keys = set(combined) | set(prev_combined)
    trade_rows = []
    hold_count = 0
    for t in sorted(all_keys, key=lambda k: -abs((combined.get(k, 0.0) - prev_combined.get(k, 0.0)))):
        prev_w = prev_combined.get(t, 0.0)
        new_w = combined.get(t, 0.0)
        delta = new_w - prev_w
        if abs(prev_w) < 1e-6 and abs(new_w) < 1e-6: continue
        if abs(delta) < 1e-4:
            hold_count += 1
            continue
        sign = "BUY " if delta > 0 else "SELL"
        color = "#1d8348" if delta > 0 else "#c0392b"
        trade_rows.append(
            f"<tr><td>{t}</td><td style='text-align:right'>{prev_w*100:.1f}%</td>"
            f"<td style='text-align:right'>{new_w*100:.1f}%</td>"
            f"<td style='text-align:right;color:{color};font-weight:600'>{sign} {abs(delta)*100:.1f}pp</td></tr>"
        )
    if trade_rows:
        hold_note = f"<p style='font-size:0.75rem;color:#888;margin:4px 0 0 0'>({hold_count} unchanged positions hidden)</p>" if hold_count else ""
        trade_html = ("<table class='alloc'><thead><tr><th>Ticker</th>"
                      "<th style='text-align:right'>Previous</th>"
                      "<th style='text-align:right'>Target</th>"
                      "<th style='text-align:right'>Trade</th></tr></thead><tbody>"
                      + "".join(trade_rows) + "</tbody></table>" + hold_note)
    else:
        trade_html = "<p style='font-size:0.85rem;color:#666'>(no rebalance trades needed; all positions unchanged from previous signal)</p>"

    # Combined target weights table
    combined_target_html = "".join(
        f"<tr><td>{t}</td><td style='text-align:right;font-weight:600'>{w*100:.1f}%</td></tr>"
        for t, w in sorted(combined.items(), key=lambda x: -x[1])
        if abs(w) > 1e-6
    )

    # Sleeve picks one-liner (for top summary)
    rpv_pick = next(iter(bq_w), CASH_TICKER) if bq_w else CASH_TICKER
    ndx_picks_str = ", ".join(ndx_diag.get("selected", [])) if ndx_diag.get("selected") else "(cash)"
    val_picks_str = ", ".join(val_selected) if val_selected else "(cash/safe)"
    sector_str = _ndx_sector_summary(ndx_diag.get("selected", [])) if ndx_diag.get("selected") else ""

    return f"""
<div class='alloc-grid'>
<div class='alloc-row' style='grid-column: 1 / -1; display: grid; grid-template-columns: 1fr; gap: 14px;'>
  <style>@media (min-width: 900px) {{ .alloc-row {{ grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) !important; }} }}</style>
  <div>
    <h4 style='background:#fff4d6;padding:8px 12px;border-radius:4px;margin:0 0 8px 0'>Final portfolio target {int(CPM_WEIGHT*100)}/{int(NDX_WEIGHT*100)}/{int(VAL_WEIGHT*100)}/{int(RPV_WEIGHT*100)}</h4>
    <div class='table-scroll'><table class='alloc'>{combined_target_html}</table></div>
  </div>
  <div>
    <h4 style='background:#e8f4fd;padding:8px 12px;border-radius:4px;margin:0 0 8px 0'>Rebalance trade (vs previous signal)</h4>
    <div class='table-scroll'>{trade_html}</div>
  </div>
</div>
<div style='grid-column: 1 / -1'>
  <details>
    <summary style='font-weight:600;cursor:pointer'>Signal diagnostics (sleeves, selection details)</summary>
    <div style='margin-top:10px'>
    <p style='font-size:0.85rem;margin:6px 0'><strong>Cross-asset Parity Momentum (CPM)</strong> ({int(CPM_WEIGHT*100)}% of capital, regime <strong>{regime}</strong>): risky basket = <strong>{basket_str}</strong>, safe = {safe}</p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>NDX</strong> ({int(NDX_WEIGHT*100)}% of capital, state <strong>{ndx_regime}</strong>): top-{NDX_SELECT_K} = {ndx_picks_str}{(' | sectors: ' + sector_str) if sector_str else ''}</p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>VAL</strong> ({int(VAL_WEIGHT*100)}% of capital, state <strong>{val_state}</strong>): picks = <strong>{val_picks_str}</strong></p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>RPV</strong> ({int(RPV_WEIGHT*100)}% of capital, state <strong>{bq_state}</strong>): holding <strong>{rpv_pick}</strong></p>
    {dd_status_html}
    <h4 style='margin-top:14px'>Sleeve-internal weights (sum to 100% of each sleeve)</h4>
    <div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));gap:14px'>
      <div><strong>CPM</strong><div class='table-scroll'><table class='alloc'>{fcp_html}</table></div></div>
      <div><strong>NDX</strong><div class='table-scroll'><table class='alloc'>{ndx_html}</table></div></div>
      <div><strong>VAL</strong><div class='table-scroll'><table class='alloc'>{val_html}</table></div></div>
      <div><strong>RPV</strong><div class='table-scroll'><table class='alloc'>{bq_html}</table></div></div>
    </div>
    </div>
  </details>
</div>
</div>
"""

def render(ctx: SimpleNamespace) -> str:
    return f"""<h2>-> This month's allocation</h2>
<div class='card'>
<div class='audit-block'>
Signal: <strong>{ctx.sig_d.date()}</strong> (last biz day of month) | Trade: <strong>T+1 OPEN</strong> ({ctx.trade_due_date}) | Age: {ctx.age_days}d | Status: {ctx.age_status}<br>
<span style='color:#888'>Data through {ctx.panel_index_last} | NDX snapshot {ctx.ndx_snapshot_date} | commit {ctx.git_sha} | built {ctx.today}</span>
</div>
{current_alloc_html(ctx.live_panel, ctx.sig_d_live, rpv_spy_rets=ctx.live_art.rpv, ndx_rets=ctx.live_art.ndx, art=ctx.live_art)}
</div>"""
