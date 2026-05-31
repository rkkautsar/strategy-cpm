"""Recompute §5.2 crisis table on BOTH-252 1995 continuous curve (research-only)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bull_qqq_live
if not hasattr(bull_qqq_live, "_vol_gate_ok"):
    bull_qqq_live._vol_gate_ok = lambda *a, **k: (True, {})
import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel

EXT1995=pd.Timestamp("1995-01-31"); END=pd.Timestamp("2026-05-22"); CLEAN=pd.Timestamp("2008-05-30")
panel=load_panel(start=EXT1995,end=END); end=min(END,panel.index[-1])
od,cy=H.load_open_close()
intraday=(cy/od-1.0).reindex(panel.index); overnight=(od/cy.shift(1)-1.0).reindex(panel.index)
cpm,fb=H.cpm_sleeve_conv(panel,intraday,overnight,EXT1995,end,"mooex"); cpm=cpm.dropna()
eq=(1+cpm).cumprod()

def episode(peak,trough):
    p=pd.Timestamp(peak); t=pd.Timestamp(trough)
    sub=eq.loc[p:t]
    depth=sub.iloc[-1]/eq.loc[:p].iloc[-1]-1.0 if len(sub) else None
    # depth as min within window relative to running peak at p
    peakval=eq.loc[:p].iloc[-1]
    win=eq.loc[p:t]
    mdd=(win/peakval-1.0).min()
    # recovery: first date after trough where eq >= peakval
    after=eq.loc[t:]
    rec=after[after>=peakval]
    rec_date=rec.index[0] if len(rec) else None
    rec_days=(rec_date-t).days if rec_date is not None else None
    return float(mdd), str(rec_date.date()) if rec_date is not None else None, rec_days

episodes={
 "LTCM_1998":("1998-07-20","1998-09-02"),
 "Dotcom_2002":("2002-05-29","2002-07-24"),
 "GFC_2008":("2008-03-14","2008-10-14"),
 "COVID_2020":("2020-03-06","2020-03-18"),
 "Y2022":("2021-11-24","2022-01-27"),
}
out={"config":"both-252","episodes":{}}
print("=== global drawdown episodes (peak->trough depth, recovery) ===")
for k,(p,t) in episodes.items():
    mdd,rd,rdays=episode(p,t)
    out["episodes"][k]={"peak":p,"trough":t,"depth":mdd,"recovery":rd,"trough_to_rec_days":rdays}
    print(f"{k:12s} peak={p} trough={t} depth={mdd*100:.2f}% rec={rd} +{rdays}d")

# within-calendar windows
def winmdd(a,b):
    s=cpm.loc[pd.Timestamp(a):pd.Timestamp(b)]
    e=(1+s).cumprod(); dd=(e/e.cummax()-1.0).min(); ret=e.iloc[-1]-1.0
    return float(dd),float(ret)
cal={"GFC_2007_10__2009_06":("2007-10-01","2009-06-30"),
     "COVID_2020_02__2020_06":("2020-02-01","2020-06-30"),
     "Y2022_bear_2022_01__2022_12":("2022-01-01","2022-12-31")}
out["within_calendar"]={}
print("\n=== within-calendar windows (MaxDD / return) ===")
for k,(a,b) in cal.items():
    mdd,ret=winmdd(a,b); out["within_calendar"][k]={"maxdd":mdd,"return":ret}
    print(f"{k:30s} MaxDD={mdd*100:.2f}% ret={ret*100:.2f}%")

# 2025 tariff worst clean DD
clean=cpm.loc[CLEAN:end]; ce=(1+clean).cumprod(); dd=ce/ce.cummax()-1.0
trough=dd.idxmin(); depth=dd.min()
peak=ce.loc[:trough].idxmax()
after=ce.loc[trough:]; pv=ce.loc[peak]; rec=after[after>=pv]
rec_date=rec.index[0] if len(rec) else None
out["clean_worst_dd_2025_tariff"]={"peak":str(peak.date()),"trough":str(trough.date()),
  "depth":float(depth),"recovery":str(rec_date.date()) if rec_date is not None else "not recovered"}
print(f"\nclean worst DD: peak={peak.date()} trough={trough.date()} depth={depth*100:.2f}% rec={rec_date}")
Path(__file__).resolve().parent.joinpath("_rebaseline_crisis_both252.json").write_text(json.dumps(out,indent=2,default=str))
print("Wrote _rebaseline_crisis_both252.json")
