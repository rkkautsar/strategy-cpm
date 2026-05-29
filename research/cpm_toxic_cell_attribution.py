#!/usr/bin/env python3
"""
CPM toxic-cell attribution: HYG-/TIP+ canary cell.

Hypothesis: CPM holds credit-sensitive / cross-asset diversifiers (EEM, VNQ,
GLD, DBC, TLT, EFA) whose correlations converge and co-crash when credit (HYG)
deteriorates - a correlation-regime-break, not idiosyncratic loss.

Cell definition: months where 13612U(HYG) < 0 AND 13612U(TIP) > 0.
(OR canary stays RISK-ON via TIP+, but HYG is negative.)

Measurement only - does not edit production files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cpm_live import (  # noqa: E402
    load_panel, run_cpm_backtest, sig_13612U, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    CORR_LOOKBACK_DAYS,
)

DIVERSIFIERS_X = ["EEM", "VNQ", "EFA", "GLD", "DBC", "TLT"]
EQUITY_X = ["QQQ", "SPHQ"]

OUT_MD = ROOT / "research" / "cpm_toxic_cell_attribution_findings.md"

_lines: list[str] = []


def emit(s: str = ""):
    print(s)
    _lines.append(s)


def flush_md():
    OUT_MD.write_text("\n".join(_lines) + "\n")
    print(f"\n[written] {OUT_MD}")


def fwd_return(close: pd.DataFrame, asset: str, start_d, end_d) -> float:
    """Compound return of asset over [start_d, end_d) holding window."""
    if asset not in close.columns:
        return np.nan
    s = close[asset].ffill()
    seg = s[(s.index >= start_d) & (s.index < end_d)]
    if len(seg) < 2:
        return np.nan
    return float(seg.iloc[-1] / seg.iloc[0] - 1)


def analyze(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, label: str):
    emit(f"\n## Window: {label}  ({start.date()} -> {end.date()})\n")
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly = close.resample("ME").last()

    cpm_rets, wh = run_cpm_backtest(panel, start, end)

    # Classify each weights_history entry by canary cell
    rows = []
    for h in wh:
        sig_d = h["sig_d"]
        msub = monthly.loc[:sig_d]
        hyg = sig_13612U(msub["HYG"]) if "HYG" in msub.columns else np.nan
        tip = sig_13612U(msub["TIP"]) if "TIP" in msub.columns else np.nan
        if pd.isna(hyg) or pd.isna(tip):
            continue
        cell = "HYG-/TIP+" if (hyg < 0 and tip > 0) else (
            "HYG+/TIP+" if (hyg > 0 and tip > 0) else (
            "HYG+/TIP-" if (hyg > 0 and tip < 0) else "HYG-/TIP-"))
        rows.append({
            "sig_d": sig_d, "apply_from": h["apply_from"], "end_apply": h["end_apply"],
            "regime": h["regime"], "safe": h["safe"], "weights": h["weights"],
            "hyg_mom": hyg, "tip_mom": tip, "cell": cell,
        })

    df = pd.DataFrame(rows)
    emit(f"Total months classified: {len(df)}")
    emit("\nCell counts:")
    emit("```")
    emit(df["cell"].value_counts().to_string())
    emit("```")

    toxic = df[df["cell"] == "HYG-/TIP+"].copy()
    riskon_clean = df[df["cell"] == "HYG+/TIP+"].copy()
    emit(f"\n**Toxic cell (HYG-/TIP+) n = {len(toxic)} months**")
    emit(f"Clean risk-on (HYG+/TIP+) n = {len(riskon_clean)} months")

    if len(toxic) == 0:
        return df, toxic, close

    # ---- 1. Enumerate toxic months: holdings + forward returns ----
    emit("\n### 1. Toxic-month enumeration (holdings + forward asset/sleeve returns)\n")
    enum_recs = []
    for _, r in toxic.iterrows():
        held = {a: w for a, w in r["weights"].items()}
        sleeve_ret = 0.0
        parts = []
        for a, w in sorted(held.items(), key=lambda x: -x[1]):
            fr = fwd_return(close, a, r["apply_from"], r["end_apply"])
            contrib = w * fr if pd.notna(fr) else np.nan
            if pd.notna(contrib):
                sleeve_ret += contrib
            parts.append(f"{a}={w*100:.0f}%(fwd {fr*100:+.1f}%)")
        held_str = ", ".join(parts)
        enum_recs.append({
            "month": r["sig_d"].date(), "regime": r["regime"],
            "hyg_mom": r["hyg_mom"], "tip_mom": r["tip_mom"],
            "held": held_str, "sleeve_fwd_ret": sleeve_ret,
            "weights": held, "apply_from": r["apply_from"], "end_apply": r["end_apply"],
        })
        emit(f"- **{r['sig_d'].date()}** [{r['regime']}] HYGmom={r['hyg_mom']:+.3f} TIPmom={r['tip_mom']:+.3f} "
             f"| held: {held_str} | sleeve fwd = {sleeve_ret*100:+.2f}%")

    sleeve_rets = np.array([e["sleeve_fwd_ret"] for e in enum_recs])
    emit(f"\nToxic-cell sleeve fwd return: mean={sleeve_rets.mean()*100:+.3f}%/mo  "
         f"median={np.median(sleeve_rets)*100:+.3f}%  "
         f"win-rate={(sleeve_rets>0).mean()*100:.0f}%  "
         f"worst={sleeve_rets.min()*100:+.2f}%  best={sleeve_rets.max()*100:+.2f}%")
    ann = (1 + sleeve_rets).prod() ** (12 / len(sleeve_rets)) - 1 if len(sleeve_rets) else np.nan
    emit(f"Annualized (geometric, in-cell only): {ann*100:+.2f}%/y")

    # ---- 2. Holdings frequency ----
    emit("\n### 2. Holdings frequency across toxic months\n")
    from collections import defaultdict
    cnt = defaultdict(int)
    wsum = defaultdict(float)
    for e in enum_recs:
        for a, w in e["weights"].items():
            cnt[a] += 1
            wsum[a] += w
    freq = pd.DataFrame({
        "count": pd.Series(cnt),
        "freq_pct": pd.Series({a: cnt[a] / len(enum_recs) * 100 for a in cnt}),
        "avg_weight_when_held": pd.Series({a: wsum[a] / cnt[a] for a in cnt}),
        "avg_weight_overall": pd.Series({a: wsum[a] / len(enum_recs) for a in cnt}),
    }).sort_values("count", ascending=False)

    def klass(a):
        if a in DIVERSIFIERS_X:
            return "cross-asset/credit-sensitive"
        if a in EQUITY_X:
            return "equity"
        return "safe/other"
    freq["class"] = [klass(a) for a in freq.index]
    emit("```")
    emit(freq.to_string(float_format=lambda x: f"{x:.2f}"))
    emit("```")
    div_share = sum(wsum[a] for a in wsum if a in DIVERSIFIERS_X)
    eq_share = sum(wsum[a] for a in wsum if a in EQUITY_X)
    other_share = sum(wsum[a] for a in wsum if a not in DIVERSIFIERS_X + EQUITY_X)
    tot = div_share + eq_share + other_share
    emit(f"\nAggregate weight share across toxic months:")
    emit(f"  cross-asset/credit-sensitive (EEM,VNQ,EFA,GLD,DBC,TLT): {div_share/tot*100:.1f}%")
    emit(f"  equity (QQQ,SPHQ): {eq_share/tot*100:.1f}%")
    emit(f"  safe/other: {other_share/tot*100:.1f}%")

    # ---- 3. Loss attribution by asset ----
    emit("\n### 3. Loss attribution by asset (sum of weight*fwd_ret contributions)\n")
    contrib_sum = defaultdict(float)
    contrib_cnt = defaultdict(int)
    for e in enum_recs:
        for a, w in e["weights"].items():
            fr = fwd_return(close, a, e["apply_from"], e["end_apply"])
            if pd.notna(fr):
                contrib_sum[a] += w * fr
                contrib_cnt[a] += 1
    total_contrib = sum(contrib_sum.values())
    attr = pd.DataFrame({
        "total_contrib_pct": pd.Series({a: v * 100 for a, v in contrib_sum.items()}),
        "n_months_held": pd.Series(contrib_cnt),
    }).sort_values("total_contrib_pct")
    attr["share_of_total_loss_pct"] = attr["total_contrib_pct"] / (total_contrib * 100) * 100 if total_contrib != 0 else np.nan
    emit(f"Sum of contributions (=cumulative sleeve return across toxic months, additive): {total_contrib*100:+.2f}%")
    emit("```")
    emit(attr.to_string(float_format=lambda x: f"{x:.3f}"))
    emit("```")

    # ---- 4. Correlation-break test ----
    emit("\n### 4. Correlation-break test (504d baseline vs forward 20d/60d realized)\n")
    daily_ret_all = close.pct_change()

    def pair_corr(a, b, asof, lookback, forward=False, start_d=None, end_d=None):
        if a == b or a not in daily_ret_all.columns or b not in daily_ret_all.columns:
            return np.nan
        if forward:
            seg = daily_ret_all[[a, b]][(daily_ret_all.index >= start_d) & (daily_ret_all.index < end_d)].dropna()
        else:
            seg = daily_ret_all[[a, b]].loc[:asof].dropna().tail(lookback)
        if len(seg) < 5:
            return np.nan
        return float(seg[a].corr(seg[b]))

    def univ_avg_corr(asof, lookback, forward=False, start_d=None, end_d=None, universe=None):
        u = universe or [a for a in RISKY_UNIVERSE if a in daily_ret_all.columns]
        if forward:
            seg = daily_ret_all[u][(daily_ret_all.index >= start_d) & (daily_ret_all.index < end_d)].dropna(how="all")
        else:
            seg = daily_ret_all[u].loc[:asof].dropna(how="all").tail(lookback)
        if len(seg) < 5:
            return np.nan
        c = seg.corr()
        vals = c.values[np.triu_indices_from(c.values, k=1)]
        vals = vals[~np.isnan(vals)]
        return float(np.mean(vals)) if len(vals) else np.nan

    def corr_table(subdf, name):
        recs = []
        for _, r in subdf.iterrows():
            held = list(r["weights"].keys())
            held_risky = [a for a in held if a in RISKY_UNIVERSE]
            sig_d, af, ea = r["sig_d"], r["apply_from"], r["end_apply"]
            # forward 20d / 60d windows from apply_from
            fut = daily_ret_all.index[daily_ret_all.index >= af]
            f20_end = fut[min(20, len(fut) - 1)] if len(fut) else ea
            f60_end = fut[min(60, len(fut) - 1)] if len(fut) else ea
            if len(held_risky) == 2:
                a, b = held_risky
                base504 = pair_corr(a, b, sig_d, CORR_LOOKBACK_DAYS)
                f20 = pair_corr(a, b, sig_d, 0, forward=True, start_d=af, end_d=f20_end)
                f60 = pair_corr(a, b, sig_d, 0, forward=True, start_d=af, end_d=f60_end)
            else:
                base504 = f20 = f60 = np.nan
            ub = univ_avg_corr(sig_d, CORR_LOOKBACK_DAYS)
            uf20 = univ_avg_corr(sig_d, 0, forward=True, start_d=af, end_d=f20_end)
            uf60 = univ_avg_corr(sig_d, 0, forward=True, start_d=af, end_d=f60_end)
            recs.append({
                "month": sig_d.date(), "pair": "+".join(held_risky) if held_risky else "(safe)",
                "pair_corr_504d": base504, "pair_corr_fwd20": f20, "pair_corr_fwd60": f60,
                "univ_corr_504d": ub, "univ_corr_fwd20": uf20, "univ_corr_fwd60": uf60,
            })
        t = pd.DataFrame(recs)
        emit(f"\n**{name}** (n={len(t)})")
        emit("```")
        emit(t.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        emit("```")
        # means
        for c in ["pair_corr_504d", "pair_corr_fwd20", "pair_corr_fwd60",
                   "univ_corr_504d", "univ_corr_fwd20", "univ_corr_fwd60"]:
            pass
        means = t[["pair_corr_504d", "pair_corr_fwd20", "pair_corr_fwd60",
                    "univ_corr_504d", "univ_corr_fwd20", "univ_corr_fwd60"]].mean()
        emit("Means:")
        emit("```")
        emit(means.to_string(float_format=lambda x: f"{x:.3f}"))
        emit("```")
        return t

    t_toxic = corr_table(toxic, "Toxic cell HYG-/TIP+ pair & universe correlations")
    if len(riskon_clean):
        t_clean = corr_table(riskon_clean, "Non-toxic risk-on HYG+/TIP+ (comparison)")
    else:
        t_clean = None

    # delta summary
    emit("\n**Correlation-break summary (fwd minus 504d baseline):**")
    def delta(t):
        if t is None or not len(t):
            return None
        return {
            "pair_fwd20-504d": (t["pair_corr_fwd20"] - t["pair_corr_504d"]).mean(),
            "pair_fwd60-504d": (t["pair_corr_fwd60"] - t["pair_corr_504d"]).mean(),
            "univ_fwd20-504d": (t["univ_corr_fwd20"] - t["univ_corr_504d"]).mean(),
            "univ_fwd60-504d": (t["univ_corr_fwd60"] - t["univ_corr_504d"]).mean(),
        }
    dt = delta(t_toxic)
    dc = delta(t_clean)
    emit("```")
    emit(f"{'metric':22s} {'toxic':>10s} {'risk-on':>10s}")
    for k in (dt or {}):
        cv = dc[k] if dc else np.nan
        emit(f"{k:22s} {dt[k]:+10.3f} {cv:+10.3f}")
    emit("```")

    # ---- 5. Co-crash test ----
    emit("\n### 5. Co-crash breadth test (held + diversifier forward-return breadth)\n")
    cc_recs = []
    for e in enum_recs:
        held = list(e["weights"].keys())
        held_risky = [a for a in held if a in RISKY_UNIVERSE]
        af, ea = e["apply_from"], e["end_apply"]
        # held-book breadth
        held_neg = sum(1 for a in held_risky if (lambda x: pd.notna(x) and x < 0)(fwd_return(close, a, af, ea)))
        # full diversifier-universe breadth
        div_present = [a for a in DIVERSIFIERS_X if a in close.columns]
        div_frs = {a: fwd_return(close, a, af, ea) for a in div_present}
        div_neg = sum(1 for v in div_frs.values() if pd.notna(v) and v < 0)
        div_valid = sum(1 for v in div_frs.values() if pd.notna(v))
        # full risky universe breadth
        ru = [a for a in RISKY_UNIVERSE if a in close.columns]
        ru_frs = {a: fwd_return(close, a, af, ea) for a in ru}
        ru_neg = sum(1 for v in ru_frs.values() if pd.notna(v) and v < 0)
        ru_valid = sum(1 for v in ru_frs.values() if pd.notna(v))
        cc_recs.append({
            "month": e["month"],
            "held_neg": f"{held_neg}/{len(held_risky)}",
            "div_neg": f"{div_neg}/{div_valid}",
            "univ_neg": f"{ru_neg}/{ru_valid}",
            "univ_neg_frac": ru_neg / ru_valid if ru_valid else np.nan,
        })
    cc = pd.DataFrame(cc_recs)
    emit("```")
    emit(cc.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    emit("```")
    emit(f"\nMean fraction of full risky universe with NEGATIVE fwd return (toxic months): "
         f"{cc['univ_neg_frac'].mean()*100:.0f}%")
    # both-held-negative rate
    both_neg = sum(1 for e in enum_recs
                   if all((lambda x: pd.notna(x) and x < 0)(fwd_return(close, a, e["apply_from"], e["end_apply"]))
                          for a in [x for x in e["weights"] if x in RISKY_UNIVERSE]) and
                   len([x for x in e["weights"] if x in RISKY_UNIVERSE]) == 2)
    n_pairs = sum(1 for e in enum_recs if len([x for x in e["weights"] if x in RISKY_UNIVERSE]) == 2)
    emit(f"Months where BOTH held risky legs negative (co-crash): {both_neg}/{n_pairs}")

    return df, toxic, close


def main():
    end = pd.Timestamp.today().normalize()

    emit("# CPM toxic-cell attribution: HYG-/TIP+ canary cell")
    emit("")
    emit("Cell = months where 13612U(HYG) < 0 AND 13612U(TIP) > 0 (RISK-ON via TIP, HYG negative).")
    emit(f"Run date: {pd.Timestamp.today().date()}")

    # CLEAN window
    clean_start = pd.Timestamp("2008-05-30")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=end)
    emit(f"\nPanel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} cols")

    try:
        analyze(panel, clean_start, end, "CLEAN (live ETF)")
    except Exception as ex:
        emit(f"\n[ERROR clean window] {type(ex).__name__}: {ex}")
        import traceback
        emit("```")
        emit(traceback.format_exc())
        emit("```")
        flush_md()
        raise

    # STRESS window (proxy-extended)
    stress_start = pd.Timestamp("1999-03-10")
    try:
        analyze(panel, stress_start, end, "STRESS (proxy-extended)")
    except Exception as ex:
        emit(f"\n[ERROR stress window] {type(ex).__name__}: {ex}")
        import traceback
        emit("```")
        emit(traceback.format_exc())
        emit("```")

    emit("\n## Verdict\n")
    emit("(see analysis sections above; verdict synthesized after run)")
    flush_md()


if __name__ == "__main__":
    main()
