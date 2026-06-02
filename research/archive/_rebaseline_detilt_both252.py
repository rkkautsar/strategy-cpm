"""Recompute §9.3 US-equity de-tilt at BOTH-252 production config (research-only)."""
import sys, json
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bull_spy_live
if not hasattr(bull_spy_live, "_vol_gate_ok"):
    bull_spy_live._vol_gate_ok = lambda *a, **k: (True, {})
import memo_review2_lookback_detilt_harness as M
from cpm_live import RISKY_UNIVERSE

RL, WL = 252, 252  # both-252 production
CLEAN_START = M.CLEAN_START
EXT_START = M.EXT_START
END = M.END

out = {"config": "both-252", "rank_lb": RL, "weight_lb": WL, "results": {}}

base_panel, base_intra, base_over = M.build_panel_and_exec([])
cash = base_panel["SHV"].ffill().pct_change().dropna()
end = min(END, base_panel.index[-1])

# production both-252 baseline
cpm_prod, _ = M.run_cpm(base_panel, base_intra, base_over, list(RISKY_UNIVERSE), RL, WL, EXT_START, end)
prod_clean = M.met(M.win(cpm_prod, CLEAN_START, end), cash)
out["results"]["prod_both252"] = prod_clean
print(f"[PROD both-252] Sh={prod_clean['sharpe']:.4f} DD={prod_clean['maxdd']*100:.2f}% Cal={prod_clean['calmar']:.4f}")

# PRIMARY de-tilt SPY
spy_univ = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
panel_spy, intra_spy, over_spy = M.build_panel_and_exec(["SPY"])
cash_spy = panel_spy["SHV"].ffill().pct_change().dropna()
end_spy = min(END, panel_spy.index[-1])
ret_spy, _ = M.run_cpm(panel_spy, intra_spy, over_spy, spy_univ, RL, WL, EXT_START, end_spy)
a2p = M.met(M.win(ret_spy, CLEAN_START, end_spy), cash_spy)
out["results"]["A2_primary_SPY"] = a2p
print(f"[A2-PRIMARY SPY both-252] Sh={a2p['sharpe']:.4f} DD={a2p['maxdd']*100:.2f}% Cal={a2p['calmar']:.4f}")

# SECONDARY swaps
sec_cfgs = {
    "QQQ->VUG":  ["VUG", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "QQQ->IWF":  ["IWF", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "SPHQ->QUAL":["QQQ", "QUAL", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "SPHQ->MTUM":["QQQ", "MTUM", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "QQQ->IWD":  ["IWD", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
}
a2_sec, a2_base = {}, {}
for name, univ in sec_cfgs.items():
    swaps = [t for t in univ if t not in RISKY_UNIVERSE]
    pnl, intra, over = M.build_panel_and_exec(swaps)
    csh = pnl["SHV"].ffill().pct_change().dropna()
    e = min(END, pnl.index[-1])
    es = M.eff_start(pnl, univ, CLEAN_START)
    ret, _ = M.run_cpm(pnl, intra, over, univ, RL, WL, es, e)
    a2_sec[name] = {"eff_start": str(es.date()), "clean_like": M.met(M.win(ret, es, e), csh)}
    a2_base[name] = M.met(M.win(cpm_prod, es, end), cash)
    print(f"[A2-SEC both-252] {name:12s} start={es.date()} Sh={a2_sec[name]['clean_like']['sharpe']:.4f} "
          f"(base {a2_base[name]['sharpe']:.4f}, d={a2_sec[name]['clean_like']['sharpe']-a2_base[name]['sharpe']:+.4f}) "
          f"DD={a2_sec[name]['clean_like']['maxdd']*100:.2f}% Cal={a2_sec[name]['clean_like']['calmar']:.4f}")
out["results"]["A2_secondary"] = a2_sec
out["results"]["A2_secondary_prod_baselines"] = a2_base

Path(__file__).resolve().parent.joinpath("_rebaseline_detilt_both252.json").write_text(json.dumps(out, indent=2, default=str))
print("Wrote _rebaseline_detilt_both252.json")
