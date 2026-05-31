"""Recompute §7.4 CPM risky contribution share on BOTH-252 (research-only)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bull_qqq_live
if not hasattr(bull_qqq_live, "_vol_gate_ok"):
    bull_qqq_live._vol_gate_ok = lambda *a, **k: (True, {})
import cpm_benchmarks_proper as B
from cpm_live import compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH

END=pd.Timestamp("2026-05-22"); EXT=pd.Timestamp("1999-03-10"); CLEAN=pd.Timestamp("2008-05-30")
panel,intraday,overnight,end=B.build_data(EXT,END)
cols=sorted(set(RISKY_UNIVERSE+SAFE_POOL+CANARY_ASSETS+[DEFAULT_CASH])&set(panel.columns))
close=panel[cols]; daily=close.ffill().pct_change()
idx=close.index
monthly=pd.DataFrame({"x":1},index=idx).groupby(pd.Grouper(freq="ME")).tail(1).index
# build weight panel held next session after each month-end signal
wmap={}
for sd in monthly:
    if sd< EXT - pd.DateOffset(days=45) or sd>end: continue
    w=compute_target_weights(close,sd)[0]
    fut=idx[idx>sd]
    if len(fut): wmap[fut[0]]=w
applied=sorted(wmap)
dfw=pd.DataFrame(0.0,index=idx,columns=RISKY_UNIVERSE)
for i,af in enumerate(applied):
    nxt=applied[i+1] if i+1<len(applied) else end
    mask=(idx>=af)&(idx<nxt)
    for a,ww in wmap[af].items():
        if a in RISKY_UNIVERSE: dfw.loc[mask,a]=ww

def shares(start):
    sel=(idx>=start)&(idx<=end)
    contrib={}
    for a in RISKY_UNIVERSE:
        c=(dfw.loc[sel,a]*daily.loc[sel,a]).sum()
        contrib[a]=c
    tot=sum(abs(v) for v in contrib.values())
    # memo uses positive contribution share; use sum of contributions
    totpos=sum(contrib.values())
    return {a: contrib[a]/totpos for a in RISKY_UNIVERSE}

out={"config":"both-252"}
for lbl,start in [("clean",CLEAN),("ext",EXT)]:
    sh=shares(start)
    out[lbl]=sh
    ordered=sorted(sh.items(),key=lambda x:-x[1])
    print(f"=== {lbl} ===")
    for a,v in ordered: print(f"  {a:5s} {v*100:.1f}%")
    top3=sum(v for _,v in ordered[:3])
    print(f"  top1={ordered[0][0]} {ordered[0][1]*100:.1f}%  top3={top3*100:.1f}%")
Path(__file__).resolve().parent.joinpath("_rebaseline_concentration_both252.json").write_text(json.dumps(out,indent=2,default=str))
print("Wrote _rebaseline_concentration_both252.json")
