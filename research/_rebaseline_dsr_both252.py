"""Recompute §8.2 DSR appendix inputs on BOTH-252 production (research-only)."""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bull_qqq_live
if not hasattr(bull_qqq_live, "_vol_gate_ok"):
    bull_qqq_live._vol_gate_ok = lambda *a, **k: (True, {})
import exec_lag_moo_validation_2026_05_30 as H
import cpm_benchmarks_proper as B
from cpm_live import perf_metrics

END = pd.Timestamp("2026-05-22"); EXT = pd.Timestamp("1999-03-10"); CLEAN = pd.Timestamp("2008-05-30")
panel, intraday, overnight, end = B.build_data(EXT, END)
cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT, end, "mooex")
clean = cpm[(cpm.index >= CLEAN) & (cpm.index <= end)].dropna()

r = clean.values
n = len(r)
sr_day = r.mean() / r.std(ddof=1)
sr_ann = sr_day * np.sqrt(252)
skew = float(stats.skew(r))
ex_kurt = float(stats.kurtosis(r, fisher=True))  # excess
print(f"n={n} SR_day={sr_day:.5f} SR_ann={sr_ann:.4f} skew={skew:.4f} exkurt={ex_kurt:.4f}")

# V_trials (grid SR variance per-day) -- selection-space property, carried from prior finding
V_trials_day = 2.094e-5  # std 0.073 ann (grid family dispersion; ~unchanged under both-252)
g = 0.5772156649  # Euler-Mascheroni

def sr0_ann(N):
    z1 = norm.ppf(1 - 1.0/N)
    z2 = norm.ppf(1 - 1.0/(N*np.e))
    sr0_day = np.sqrt(V_trials_day) * ((1-g)*z1 + g*z2)
    return sr0_day, sr0_day*np.sqrt(252)

def dsr_z(N):
    sr0_day, sr0_a = sr0_ann(N)
    denom = np.sqrt(1 - skew*sr_day + ((ex_kurt+3-1)/4.0)*sr_day**2)
    z = (sr_day - sr0_day)*np.sqrt(n-1)/denom
    dsr = norm.cdf(z)
    return sr0_a, dsr, z

out = {"config": "both-252", "SR_hat_day": float(sr_day), "SR_ann": float(sr_ann),
       "n_daily": n, "skew": skew, "excess_kurtosis": ex_kurt,
       "V_trials_day": V_trials_day, "by_N": {}}
print("\nN     SR0_ann   DSR      z")
for N in (40, 80, 200, 500, 1000, 2000):
    sr0_a, dsr, z = dsr_z(N)
    out["by_N"][N] = {"sr0_ann": float(sr0_a), "dsr": float(dsr), "z": float(z)}
    print(f"{N:5d} {sr0_a:7.3f}  {dsr:.4f}  {z:.2f}")

# monthly frame
m = clean.resample("ME").apply(lambda x: (1+x).prod()-1).dropna()
mr = m.values
sr_m = mr.mean()/mr.std(ddof=1)
nm = len(mr)
skew_m = float(stats.skew(mr)); kurt_m = float(stats.kurtosis(mr, fisher=True))
# monthly V_trials ~ daily*21
V_m = V_trials_day*21
def dsr_z_m(N):
    z1 = norm.ppf(1-1.0/N); z2 = norm.ppf(1-1.0/(N*np.e))
    sr0_m = np.sqrt(V_m)*((1-g)*z1+g*z2)
    denom = np.sqrt(1 - skew_m*sr_m + ((kurt_m+3-1)/4.0)*sr_m**2)
    z = (sr_m - sr0_m)*np.sqrt(nm-1)/denom
    return norm.cdf(z), z
print(f"\nMonthly: n={nm} SR_m={sr_m:.4f} skew={skew_m:.4f} exkurt={kurt_m:.4f}")
zs=[]
for N in (40,80,200,500,1000,2000):
    dsr,z=dsr_z_m(N); zs.append(z)
    print(f"  N={N:5d} DSR={dsr:.4f} z={z:.2f}")
out["monthly"]={"n":nm,"sr_m":float(sr_m),"skew":skew_m,"excess_kurtosis":kurt_m,"z_range":[float(min(zs)),float(max(zs))]}
zd=[v["z"] for v in out["by_N"].values()]
out["daily_z_range"]=[float(min(zd)),float(max(zd))]
print(f"\ndaily z range [{min(zd):.2f},{max(zd):.2f}]  monthly z range [{min(zs):.2f},{max(zs):.2f}]")
Path(__file__).resolve().parent.joinpath("_rebaseline_dsr_both252.json").write_text(json.dumps(out,indent=2,default=str))
print("Wrote _rebaseline_dsr_both252.json")
