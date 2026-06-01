"""Recompute 1995-extended headline on BOTH-252 production (research-only)."""
import sys, json
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bull_spy_live
if not hasattr(bull_spy_live, "_vol_gate_ok"):
    bull_spy_live._vol_gate_ok = lambda *a, **k: (True, {})
import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel, perf_metrics, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH

EXT1995 = pd.Timestamp("1995-01-31"); EXT1999 = pd.Timestamp("1999-03-10")
CLEAN = pd.Timestamp("2008-05-30"); END = pd.Timestamp("2026-05-22")

def met(s, cash):
    m = perf_metrics(s, cash)
    return {k: m.get(v) for k, v in {"sharpe":"sharpe","cagr":"cagr","vol":"vol","maxdd":"max_drawdown","calmar":"calmar","martin":"martin","ulcer":"ulcer","excess_sharpe":"excess_sharpe"}.items()}
def win(s,a,b): return s.loc[(s.index>=a)&(s.index<=b)]

panel = load_panel(start=EXT1995, end=END)
end = min(END, panel.index[-1])
cash = panel["SHV"].ffill().pct_change().dropna()
od, cy = H.load_open_close()
intraday = (cy/od-1.0).reindex(panel.index)
overnight = (od/cy.shift(1)-1.0).reindex(panel.index)
cpm_full, fb = H.cpm_sleeve_conv(panel, intraday, overnight, EXT1995, end, "mooex")
cpm_full = cpm_full.dropna()
print(f"curve {cpm_full.index[0].date()}->{cpm_full.index[-1].date()} rebal real/fb={fb}")
out={"config":"both-252"}
for lbl,start in [("clean",CLEAN),("ext1999",EXT1999),("ext1995",EXT1995)]:
    m=met(win(cpm_full,start,end),cash)
    out[lbl]=m
    print(f"{lbl:8s} Sh={m['sharpe']:.4f} CAGR={m['cagr']*100:.2f}% Vol={m['vol']*100:.2f}% "
          f"DD={m['maxdd']*100:.2f}% Cal={m['calmar']:.4f} Mar={m['martin']:.4f} Ulc={m['ulcer']*100:.2f}% exSh={m.get('excess_sharpe')}")
Path(__file__).resolve().parent.joinpath("_rebaseline_ext1995_both252.json").write_text(json.dumps(out,indent=2,default=str))
print("Wrote _rebaseline_ext1995_both252.json")
