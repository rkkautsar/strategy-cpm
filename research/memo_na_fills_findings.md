# Memo n/a fills -- two computable cells in cpm_bull_two_sleeve_memo.md

Role: analyst (read-only re production; research/ artifacts only; NO production
edit, NO commit, NO memo edit). Throwaway harness `research/memo_na_fills.py`
plus the existing canonical factorial JSON `research/factorial_decomposition_2026_05_30.json`.

Goal: replace the two "n/a" cells that ARE computable so no lazy n/a remains.

1. Section 5.1/5.2 sleeve table -- CPM and BULL standalone EXTENDED-window
   Excess Sharpe vs SHV.
2. Section 12.6.2 BULL factorial -- K x V interaction EXTENDED value.

Both are computed on the SAME canonical post-tidy harness that produced the
memo's existing, confirmed columns, so the new cells are internally consistent
with their neighbors.

## Item 1 -- CPM and BULL standalone EXTENDED Excess Sharpe vs SHV

Harness: `exec_lag_moo_validation_2026_05_30` (module H), T+1 MOO exact
(`mooex`, real auto_adjust opens), 10 bps/side post-cost, BULL slow vol gate
rv_60d < rv_252d. Excess = `cpm_live.perf_metrics` excess_sharpe = annualized
mean(daily - SHV_daily) / annualized std(daily - SHV_daily), SHV proxy =
stitched VFISX pre-ETF. This is the identical definition and cash benchmark the
memo's existing clean Excess Sharpe column uses. Windows: clean
2008-05-30..2026-05-22; ext 1999-03-10..2026-05-22. Standalone sleeve series
sliced from the common (CPM-intersect-BULL) index, exactly as the memo harness.

### Anchor gate (confirmed before reporting derived values)

| Quantity | Computed | Memo / anchor | Verdict |
|---|---:|---|---|
| CPM clean raw Sharpe | 1.1910 | 1.1910 | CONFIRMED |
| CPM clean MaxDD / Calmar | -12.67% / 1.0615 | -12.67% / 1.0615 | CONFIRMED |
| CPM ext raw Sharpe | 1.2142 | 1.2142 (anchor) | CONFIRMED |
| CPM ext MaxDD / Calmar | -15.93% / 0.8608 | -15.93% / 0.8608 | CONFIRMED |
| BULL ext raw Sharpe | 0.9196 | ~0.920 (anchor) | CONFIRMED |
| CPM clean Excess Sharpe (xref) | 1.0719 | 1.072 | CONFIRMED |
| BULL clean Excess Sharpe (xref) | 0.9552 | 0.955 | CONFIRMED |

All raw-Sharpe anchors reproduce exactly, and the existing clean Excess Sharpe
column reproduces to 3 decimals, so the harness is the right one and the derived
ext Excess Sharpe values are on the same basis.

### Derived (the fills)

| Sleeve | Window | Raw Sharpe | Excess Sharpe vs SHV |
|---|---|---:|---:|
| CPM | ext | 1.2142 | **1.006** |
| BULL | ext | 0.920 | **0.700** |

Full precision: CPM ext excess 1.00616; BULL ext excess 0.69955.

So the two memo n/a cells (Section 5.2 Excess Sharpe column) become:
**CPM = 1.006, BULL = 0.700.**

Context: the extended window adds the 1999-2008 segment (dot-com bust, GFC ramp)
on partly proxy-backed data. CPM's excess Sharpe is essentially flat clean->ext
(1.072 -> 1.006); BULL's drops more (0.955 -> 0.700), consistent with BULL's
weaker extended raw Sharpe (1.081 -> 0.920) over the proxy-era stress.

## Item 2 -- BULL K x V interaction, EXTENDED value (Section 12.6.2)

Source: canonical factorial JSON `research/factorial_decomposition_2026_05_30.json`
(the run that produced `factorial_decomposition_findings.md` and Section 12.6.2).
Interaction effect (balanced 2^3, coded +-1) =
mean(cells where codeK*codeV = +1) - mean(cells where codeK*codeV = -1), the
SAME estimator that produces the published V x S values.

### Method validation against published 12.6.2 numbers (full precision)

| Quantity | Computed | Memo | Verdict |
|---|---:|---:|---|
| V x S clean dCalmar | +0.1433 | +0.143 | CONFIRMED |
| V x S ext dCalmar | +0.1151 | +0.115 | CONFIRMED |
| S main effect clean dCalmar | +0.1367 | +0.137 | CONFIRMED |
| V main effect clean dSharpe | +0.0810 | +0.081 | CONFIRMED |
| K main effect clean dCalmar | +0.0482 | +0.048 | CONFIRMED |

Estimator confirmed: every other 12.6.2 BULL value reproduces from this JSON.

### The K x V discrepancy and the fill

The K x V interaction by metric/window (full precision, same estimator):

| Metric | CLEAN | EXT |
|---|---:|---:|
| Sharpe | -0.0361 | -0.0408 |
| Calmar | -0.0203 | -0.0338 |

The memo's published clean K x V = **-0.036 is the CLEAN Sharpe interaction
(-0.0361)**, not the Calmar interaction (-0.0203) -- even though it sits in a
column labeled "dCalmar" next to the V x S Calmar values. The
`factorial_decomposition_findings.md` text ("K x V = -0.036") carried the same
Sharpe number into a Calmar-context sentence. So the published clean value is a
Sharpe interaction.

Following the task instruction "same method as the clean interaction" (i.e. the
quantity that actually equals the published -0.036), the EXTENDED fill is the
**K x V EXT Sharpe interaction = -0.041** (-0.0408).

- Consistent-with-published-clean fill: clean -0.036, **ext -0.041** (both
  Sharpe interactions).
- If the column label "dCalmar" is taken literally instead, the internally
  consistent pair is clean -0.020, ext -0.034 (both Calmar). In that reading the
  published clean -0.036 is itself wrong and would also need correcting.

Recommended fill (matches the published clean -0.036, no memo-edit by analyst):
**K x V ext = -0.041**, with a flag that clean -0.036 / ext -0.041 are Sharpe
interactions mislabeled in a dCalmar column (Calmar equivalents -0.020 / -0.034).
Sign and magnitude are stable across both metrics and windows (small negative),
so the qualitative reading -- K x V is a minor negative interaction, dwarfed by
V x S -- is unchanged either way.

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
uv run python research/memo_na_fills.py        # Item 1 (anchor-gated)
# Item 2 from canonical JSON:
uv run python - <<'PY'
import json, itertools
c=json.load(open('research/factorial_decomposition_2026_05_30.json'))['bull']['cells']
s=lambda x:1 if x=='1' else -1
def inter(a,b,w,m):
    p=[v[w][m] for k,v in c.items() if s(k[a])*s(k[b])>0]
    q=[v[w][m] for k,v in c.items() if s(k[a])*s(k[b])<0]
    return sum(p)/len(p)-sum(q)/len(q)
for m in ('sharpe','calmar'):
    print('KxV',m,'clean',round(inter(0,1,'CLEAN',m),4),'ext',round(inter(0,1,'EXT',m),4))
PY
```

## Caveats / confidence

- Item 1: HIGH confidence. All raw-Sharpe anchors and the existing clean Excess
  Sharpe column reproduce exactly on this harness; derived ext values are the
  same metric on the same series. Ext segment is partly proxy-backed pre-2006/08
  (inherent to the memo's extended window, not new to this fill).
- Item 2: HIGH confidence on the numbers; MEDIUM on which one the memo "wants"
  because of the Sharpe-vs-Calmar column-label inconsistency in the source memo.
  Reported both; recommended -0.041 to stay consistent with the already-published
  clean -0.036.
- No production files, dashboard, or memo edited. No commit. Analyst does not
  apply the fills; a fixer would paste CPM ext Excess Sharpe 1.006, BULL ext
  Excess Sharpe 0.700, and K x V ext -0.041 (with the label flag).

## Next handoff

fixer -- to paste the three values into cpm_bull_two_sleeve_memo.md (Section 5.2
Excess Sharpe: CPM 1.006, BULL 0.700; Section 12.6.2 K x V ext -0.041) and,
optionally, resolve the dCalmar/Sharpe column-label inconsistency on the K x V
row.
