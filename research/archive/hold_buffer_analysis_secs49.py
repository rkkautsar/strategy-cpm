#!/usr/bin/env python3
"""Remaining analysis sections 4-9."""
import sys; sys.path.insert(0, "/Users/rkautsar/personal/scripts")
import numpy as np, pandas as pd
from strategy_fcp.fcp_live import (
    load_panel, faber_sma_xs, zscore,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, PP_ASSETS, DEFAULT_CASH, TOP_K_CANDIDATES,
)

panel = load_panel(start=pd.Timestamp("2006-01-01"), end=pd.Timestamp("2026-05-31"))
cols = sorted(set(RISKY_UNIVERSE+SAFE_POOL+CANARY_ASSETS+PP_ASSETS+[DEFAULT_CASH])&set(panel.columns))
close = panel[cols]
monthly_close = close.resample("ME").last()
signal_dates = monthly_close.index[monthly_close.index >= pd.Timestamp("2008-01-01")]

# ---- z-score distribution ----
rows = []
for sig_d in signal_dates:
    sub = monthly_close.loc[:sig_d]
    if len(sub) < 10: continue
    score = faber_sma_xs(sub)
    avail = [t for t in RISKY_UNIVERSE if t in score.index and pd.notna(score[t])]
    if len(avail) < 3: continue
    sa = score.loc[avail]; za = zscore(sa)
    sv = za.sort_values(ascending=False).values
    rows.append({"date":sig_d,"year":sig_d.year,
                 "z_range":sv[0]-sv[-1],
                 "gap_top1_top2":sv[0]-sv[1] if len(sv)>=2 else np.nan,
                 "gap_top2_top3":sv[1]-sv[2] if len(sv)>=3 else np.nan,
                 "n_positive_score":(sa>0).sum()})
zdist = pd.DataFrame(rows)
print("\n=== Z-SCORE DISTRIBUTION SUBWINDOW SUMMARY ===")
for label,y0,y1 in [("2008-2014",2008,2014),("2015-2019",2015,2019),("2020-2026",2020,2026)]:
    sub = zdist[(zdist.year>=y0)&(zdist.year<=y1)]
    print(f"  {label}: z_range={sub.z_range.mean():.3f}  gap_top1v2={sub.gap_top1_top2.mean():.3f}  gap_top2v3={sub.gap_top2_top3.mean():.3f}  n_pos={sub.n_positive_score.mean():.1f}")

# ---- candidate stability ----
prev_c = None; rows2 = []
for sig_d in signal_dates:
    sub = monthly_close.loc[:sig_d]
    if len(sub)<10: prev_c=None; continue
    score = faber_sma_xs(sub)
    avail = [t for t in RISKY_UNIVERSE if t in score.index and pd.notna(score[t])]
    if not avail: continue
    sa = score.loc[avail]; ranked = sa.sort_values(ascending=False)
    top_k = max(2,min(TOP_K_CANDIDATES,len(ranked)))
    positive = set(ranked.iloc[:top_k][lambda s: s>0].index)
    if prev_c is not None:
        union = positive|prev_c
        j = len(positive&prev_c)/len(union) if union else 1.0
        rows2.append({"date":sig_d,"year":sig_d.year,"jaccard":j,"new_entrants":len(positive-prev_c)})
    prev_c = positive
stab = pd.DataFrame(rows2)
print("\n=== CANDIDATE STABILITY SUBWINDOW SUMMARY ===")
for label,y0,y1 in [("2008-2014",2008,2014),("2015-2019",2015,2019),("2020-2026",2020,2026)]:
    sub = stab[(stab.year>=y0)&(stab.year<=y1)]
    print(f"  {label}: avg_jaccard={sub.jaccard.mean():.3f}  avg_new_entrants/mo={sub.new_entrants.mean():.2f}")

# ---- 2009-2010 cross-section ----
a6 = [a for a in ["IGM","QQQ","GLD","TLT","SPHQ","SPY"] if a in monthly_close.columns]
r6 = monthly_close.loc["2009-01":"2010-04",a6].pct_change().dropna()*100
print("\n=== 2009-2010 MONTHLY RETURNS (%) ===")
print("  Date      "+"".join(f"  {a:>7}" for a in a6))
DIFF_6 = {"2009-08","2009-09","2009-10","2009-11","2009-12","2010-01"}
for dt,row in r6.iterrows():
    flag=" *** DIFF" if dt.strftime("%Y-%m") in DIFF_6 else ""
    print(f"  {dt.strftime('%Y-%m'):<10}"+"".join(f"  {row.get(a,np.nan):>+7.2f}" for a in a6)+flag)
ph=monthly_close.loc["2009-07":"2010-02",a6]
if len(ph)>1:
    cum=(ph/ph.iloc[0]-1)*100
    print("  Cumulative Aug09-Feb10:")
    for a in a6: print(f"    {a}: {cum[a].iloc[-1]:+.1f}%")

# ---- 2012 cross-section ----
a7=[a for a in ["SPHQ","TLT","QQQ","GLD","SPMO","SPY"] if a in monthly_close.columns]
r7=monthly_close.loc["2012-01":"2013-03",a7].pct_change().dropna()*100
print("\n=== 2012-2013 MONTHLY RETURNS (%) ===")
print("  Date      "+"".join(f"  {a:>7}" for a in a7))
DIFF_12={"2012-03","2012-04","2012-09","2012-10","2012-11","2012-12"}
for dt,row in r7.iterrows():
    flag=" *** DIFF" if dt.strftime("%Y-%m") in DIFF_12 else ""
    print(f"  {dt.strftime('%Y-%m'):<10}"+"".join(f"  {row.get(a,np.nan):>+7.2f}" for a in a7)+flag)

# ---- 2019-2020 cross-section ----
a8=[a for a in ["GLD","TLT","SPHQ","VEA","QQQ","SPY","IEF"] if a in monthly_close.columns]
r8=monthly_close.loc["2019-09":"2020-06",a8].pct_change().dropna()*100
print("\n=== 2019-2020 MONTHLY RETURNS (%) ===")
print("  Date      "+"".join(f"  {a:>7}" for a in a8))
DIFF_20={"2019-12","2020-01"}
for dt,row in r8.iterrows():
    flag=" *** DIFF" if dt.strftime("%Y-%m") in DIFF_20 else ""
    print(f"  {dt.strftime('%Y-%m'):<10}"+"".join(f"  {row.get(a,np.nan):>+7.2f}" for a in a8)+flag)
