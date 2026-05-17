"""Test 4 canary rule variants on FCP-15 production engine.

Variants:
  CURRENT  : SPY+TIP both must be positive (status quo)
  A_AVOIDSTAG : Risk-on UNLESS state is (SPY+, TIP-). All other states risk-on.
  B_HYG    : SPY+TIP+HYG. Defensive ONLY when state is (SPY+, TIP-, HYG-)
             [i.e. stagflation + credit weakness = real defensive trigger].
             Default risk-on otherwise.
  C_REBOUND: Risk-on if (SPY+ AND TIP+) OR (SPY- AND TIP+) [rebound state].
             Defensive otherwise.

Compare on live-only 18y window using full FCP engine (TOP_K=7, HOLD_BUFFER=2.5,
vol-target 10%, 10bps/side).
"""
from __future__ import annotations
import sys
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fcp_live import (  # type: ignore
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    TARGET_VOL, HOLD_BUFFER, CORR_LOOKBACK_DAYS, VOL_LOOKBACK_DAYS,
    MAX_LEVERAGE, COST_BPS_PER_SIDE, TOP_K_CANDIDATES,
    load_panel, faber_sma_xs, min_vol_pair, zscore, best_safe, sig_13612W,
    perf_metrics,
)


# ---- Canary rule signatures: (canary_states: dict[str, bool]) -> bool ----

def rule_current(s):
    """SPY+TIP both must be positive."""
    return s.get("SPY", False) and s.get("TIP", False)


def rule_a_avoid_stag(s):
    """Risk-on UNLESS state is SPY+ TIP-. All other states risk-on."""
    spy = s.get("SPY", False)
    tip = s.get("TIP", False)
    # Only defensive when SPY+ and TIP-
    if spy and not tip:
        return False
    return True


def rule_b_hyg(s):
    """SPY+TIP+HYG. Defensive ONLY when SPY+ TIP- HYG-. Risk-on otherwise."""
    spy = s.get("SPY", False)
    tip = s.get("TIP", False)
    hyg = s.get("HYG", False)
    # Defensive triple condition
    if spy and (not tip) and (not hyg):
        return False
    return True


def rule_c_rebound(s):
    """Risk-on if (SPY+ AND TIP+) OR (SPY- AND TIP+)."""
    spy = s.get("SPY", False)
    tip = s.get("TIP", False)
    return tip and (spy or not spy)  # i.e. simply TIP+ alone

# Wait that's just TIP positive. Let me write the actual rebound rule:

def rule_c_rebound(s):
    """Risk-on if (+/+) OR (-/+). Defensive on (+/-) stagflation and (-/-) capitulation."""
    spy = s.get("SPY", False)
    tip = s.get("TIP", False)
    if spy and tip:    # +/+
        return True
    if (not spy) and tip:  # -/+
        return True
    return False


RULES = {
    "CURRENT  (SPY+TIP both+)": (rule_current, ["SPY", "TIP"]),
    "A_AVOIDSTAG (NOT SPY+,TIP-)": (rule_a_avoid_stag, ["SPY", "TIP"]),
    "B_HYG (defens ONLY +/-/-)": (rule_b_hyg, ["SPY", "TIP", "HYG"]),
    "C_REBOUND (+/+ OR -/+)": (rule_c_rebound, ["SPY", "TIP"]),
}


def compute_target_weights_custom(close, sig_d, canary_rule, canary_assets, prev_pair=None,
                                   universe=None, safe_pool=None,
                                   top_k=TOP_K_CANDIDATES,
                                   hold_buffer=HOLD_BUFFER,
                                   corr_lb=CORR_LOOKBACK_DAYS):
    """Compute target weights using custom canary rule."""
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL

    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    # Compute canary state from arbitrary canary set
    canary_state = {}
    for c in canary_assets:
        if c not in monthly.columns:
            return {safe: 1.0}, None, "DEFENSIVE", safe
        s = sig_13612W(monthly[c])
        if pd.isna(s):
            return {safe: 1.0}, None, "DEFENSIVE", safe
        canary_state[c] = (s > 0)

    if not canary_rule(canary_state):
        return {safe: 1.0}, None, "DEFENSIVE", safe

    # Risk-on: do pair selection
    score = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in score.index and pd.notna(score[t])
             and t in close.columns]
    if len(avail) < 2:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    score_avail = score[avail].sort_values(ascending=False)
    top_half = score_avail.head(max(2, len(avail) // 2)).index.tolist()
    pos = [t for t in top_half if score_avail[t] > 0]

    if len(pos) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    candidates = pos[:top_k]

    if len(candidates) == 1:
        return {candidates[0]: 0.5, safe: 0.5}, None, "PARTIAL_SAFE", safe

    # Min-variance pair from candidates
    pair = min_vol_pair(close, candidates, corr_lb)
    if pair is None:
        return {candidates[0]: 0.5, safe: 0.5}, None, "PARTIAL_SAFE", safe

    # Hold buffer: keep prev pair unless new is materially better
    if prev_pair is not None and prev_pair[0] in score_avail and prev_pair[1] in score_avail:
        prev_in_top = prev_pair[0] in top_half and prev_pair[1] in top_half
        if prev_in_top:
            z = zscore(score_avail)
            new_z_mean = (z[pair[0]] + z[pair[1]]) / 2 if pair[0] in z and pair[1] in z else 0
            prev_z_mean = (z[prev_pair[0]] + z[prev_pair[1]]) / 2
            if new_z_mean - prev_z_mean < hold_buffer:
                pair = prev_pair

    a, b = pair
    return {a: 0.5, b: 0.5}, pair, "RISK_ON", safe


def run_fcp_backtest_custom(panel, start, end, canary_rule, canary_assets,
                              apply_vol_target=True, cost_bps=COST_BPS_PER_SIDE):
    """Run FCP backtest with custom canary rule."""
    extra = [c for c in canary_assets if c not in CANARY_ASSETS]
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + extra + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    prev_pair = None
    regime_log = []

    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = compute_target_weights_custom(
            close, sig_d, canary_rule, canary_assets, prev_pair=prev_pair)
        regime_log.append((sig_d, regime))
        prev_pair = new_pair
        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else end
        else:
            end_apply = end
        weights_history.append({"apply_from": apply_from, "end_apply": end_apply,
                                "weights": w, "sig_d": sig_d, "regime": regime, "safe": safe})

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])

    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    if apply_vol_target:
        realized = raw_returns.rolling(VOL_LOOKBACK_DAYS).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEVERAGE).shift(1).fillna(1.0)
        raw_returns = raw_returns * scale

    rets = raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)]
    pct_ro = sum(1 for _, r in regime_log if r == "RISK_ON") / max(1, len(regime_log)) * 100
    pct_ps = sum(1 for _, r in regime_log if r == "PARTIAL_SAFE") / max(1, len(regime_log)) * 100
    pct_def = sum(1 for _, r in regime_log if r == "DEFENSIVE") / max(1, len(regime_log)) * 100
    return rets, weights_history, pct_ro, pct_ps, pct_def


def main():
    out_path = Path(__file__).parent / "canary_rule_variants.log"
    log_lines = []

    def log(s=""):
        log_lines.append(s)
        print(s)

    log("=" * 100)
    log("CANARY RULE VARIANTS BACKTEST")
    log("Universe: FCP-15.  Engine: TOP_K=7, HOLD_BUFFER=2.5, vol-target 10%, 10bps/side")
    log("Window: Live 2008-09-30 -> today")
    log("=" * 100)

    panel = load_panel(start=pd.Timestamp("2007-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")
    log("")

    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]

    results = []

    for label, (rule_fn, canaries) in RULES.items():
        # Check canary availability
        missing = [c for c in canaries if c not in panel.columns]
        if missing:
            log(f"SKIP {label}: missing {missing}")
            continue
        log(f"Running: {label}  canaries={canaries}")
        rets, _wh, pct_ro, pct_ps, pct_def = run_fcp_backtest_custom(
            panel, start, end, rule_fn, canaries)
        m = perf_metrics(rets)
        log(f"  Sh={m['sharpe']:+.3f}  CAGR={m['cagr']*100:+.2f}%  Vol={m['vol']*100:.2f}%  "
            f"DD={m['max_drawdown']*100:+.2f}%  pct_RO={pct_ro:.1f}%  pct_PS={pct_ps:.1f}%  "
            f"pct_DEF={pct_def:.1f}%")
        results.append((label, m, pct_ro, pct_ps, pct_def))

    log("")
    log("=" * 100)
    log("SUMMARY (sorted by Sharpe)")
    log("=" * 100)
    log("")
    log("  Rule                                    Sharpe    CAGR%    Vol%    MaxDD%    %RO  %PS  %DEF")
    log("  " + "-" * 105)
    for label, m, ro, ps, df_ in sorted(results, key=lambda r: -r[1]["sharpe"]):
        log(f"  {label:40s}  {m['sharpe']:+.3f}  {m['cagr']*100:+7.2f}  {m['vol']*100:6.2f}  "
            f"{m['max_drawdown']*100:+7.2f}   {ro:5.1f}  {ps:4.1f}  {df_:5.1f}")
    log("")
    log("=" * 100)

    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
