import sys, json
from pathlib import Path
import pandas as pd, numpy as np
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
import cpm_live as C
from cpm_live import load_panel, perf_metrics, RISKY_UNIVERSE
import build_dashboard as B
from ndx_sleeve_live import load_ndx_panel
CLEAN=pd.Timestamp("2008-05-30"); END=pd.Timestamp("2026-05-22")
ps=min(CLEAN-pd.DateOffset(years=20),pd.Timestamp("1995-01-01"))
panel=load_panel(start=ps,end=None,live=False)
cash=panel["SHV"].ffill().pct_change().dropna()
npp=load_ndx_panel()
end=min(END,panel.index[-1])
print("RISKY_UNIVERSE:",RISKY_UNIVERSE)
print("CANARY:",C.CANARY_ASSETS,"panel_last",panel.index[-1].date(),"end",end.date())
art=B.build_artifacts(panel,npp,CLEAN,end,include_records=True)
def show(n,d): print(f"{n:32s} Sh {d['sharpe']:.4f} ExSh {d.get('excess_sharpe',float('nan')):.4f} CAGR {d['cagr']*100:.2f}% Vol {d['vol']*100:.2f}% DD {d['max_drawdown']*100:.2f}% Calmar {d['calmar']:.4f} Martin {d['martin']:.4f}")
# two-sleeve 60/40 (no NDX)
two=0.6*art.cpm+0.4*art.bull
show("CPM-BULL 60/40 (two-sleeve)",perf_metrics(two,cash))
show("CPM solo (clean)",perf_metrics(art.cpm,cash))
show("PROD 60/20/20",perf_metrics(art.blend,cash))
# CPM concentration: per-asset share of RISKY sleeve exposure across signal dates
from collections import defaultdict
acc=defaultdict(float); tot=0.0
for rec in art.cpm_records:
    for a,w in rec["weights"].items():
        if a in RISKY_UNIVERSE:
            acc[a]+=w; tot+=w
print("\nCPM concentration (share of risky exposure):")
for a,v in sorted(acc.items(),key=lambda kv:-kv[1]):
    print(f"  {a:5s} {v/tot*100:.1f}%")
# alpha/beta
bb4=B.bench_bb4_blend(panel,CLEAN,end)
b2=B.bench_aaa_tip(panel,CLEAN,end); b3=B.bench_haa_simple(panel,CLEAN,end,asset="SPY")
common=b2.index.intersection(b3.index); bb1=(0.6*b2.reindex(common).fillna(0)+0.4*b3.reindex(common).fillna(0))
b5=B.bench_qqq_12mo_trend(panel,CLEAN,end)
spy=panel["SPY"].ffill().pct_change().loc[CLEAN:end].fillna(0.0)
qqq=panel["QQQ"].ffill().pct_change().loc[CLEAN:end].fillna(0.0)
print("\nAlpha/beta/corr (OLS daily):")
for lab,strat,bench,bl in [("PROD",art.blend,bb4,"BB4"),("PROD",art.blend,bb1,"BB1"),
    ("CPM",art.cpm,b2,"B2 AAA+TIP"),("BULL",art.bull,b3,"B3 HAA-S SPY"),("NDX",art.ndx,qqq,"QQQ bh")]:
    r=B.alpha_beta_corr(strat,bench)
    print(f"  {lab:5s} vs {bl:12s} alpha {r['alpha_ann_pct']:+.2f}%/yr beta {r['beta']:.3f} corr {r['corr']:.3f}")
