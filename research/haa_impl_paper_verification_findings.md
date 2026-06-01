# HAA Benchmark: Paper-vs-Implementation Verification + 13612 Metric Resolution

Role: analyst (read-only re production/memo; research/ only; no commit). Date: 2026-06-01.

## Question

Does the canonical-HAA benchmark used as the memo's headline peer
(`research/cpm_haa_benchmark_ladder.py`) faithfully match the published HAA paper,
and is there a momentum-metric naming bug (unweighted `13612U` vs VAA/DAA's
weighted `13612W`)?

## Method / sources

- Paper spec extracted from Keller & Keuning (2023), "Dual and Canary Momentum
  with Rising Yields/Inflation: Hybrid Asset Allocation (HAA)", SSRN 4346906, via
  the author-adjacent canonical recipe at TrendXplorer (indexswingtrader.blogspot.com,
  Wouter Keller's own collaborator blog) and AllocateSmartly's HAA writeup. Extracted
  full "HAA recipe" text verbatim (tavily extract).
- Code inspected with `read`/`grep`: `cpm_live.py` (`sig_13612U`, `best_safe`,
  `compute_target_weights`), `research/cpm_haa_benchmark_ladder.py` (`haa_wf`,
  `param_wf`), and benchmark output `research/cpm_haa_benchmark_ladder.json`.

## CRUX RESOLUTION: 13612U vs 13612W

The HAA paper deliberately uses the **UNWEIGHTED** average. This is the opposite
of VAA/DAA. Verbatim from the canonical HAA recipe (step 1):

> "Calculate the momentum of each asset ... where momentum is the **(unweighted)
> average total return** over the past 1, 3, 6, and 12 months (**13612U**) and
> rank assets based on their momentums..."

The suffix "U" in `13612U` literally denotes **Unweighted**. VAA and DAA (earlier
Keller papers) use `13612W` = `(12*r1 + 4*r3 + 2*r6 + 1*r12)` (Weighted). HAA
switched to the unweighted variant by design. (One secondary aggregator,
bestfolio.app, mislabels HAA as "13612W" -- that is an error; the primary
author-adjacent source and the paper name it 13612U/unweighted.)

What the code computes (`cpm_live.py:269-281`):

```python
def sig_13612U(p: pd.Series) -> float:
    """Canonical Keller HAA 13612U momentum: simple unweighted average of
    1/3/6/12-month total returns. Matches Keller & Keuning HAA paper (2022)."""
    ...
    r1 = last / p.iloc[-2] - 1
    r3 = last / p.iloc[-4] - 1
    r6 = last / p.iloc[-7] - 1
    r12 = last / p.iloc[-13] - 1
    return (r1 + r3 + r6 + r12) / 4.0          # cpm_live.py:281  UNWEIGHTED
```

Memo agrees (`cpm_memo.md:77`): `m_13612U = (r_1 + r_3 + r_6 + r_12) / 4`.

| Item | Value |
|---|---|
| (a) What `cpm_live.sig_13612U` computes | `(r1+r3+r6+r12)/4` = **unweighted** simple average |
| (b) What the HAA paper specifies | `13612U` = **unweighted** average total return over 1/3/6/12m |
| (c) Match? | **YES, exact.** No fidelity bug. |

The premise that "VAA/DAA's canonical momentum is weighted 13612W" is true *for
VAA/DAA*, but irrelevant to HAA: HAA's published spec is explicitly the unweighted
13612U. There is **no discrepancy** -- the impl, the memo description, and the paper
all agree on unweighted. No re-run / impact estimate is required (no mismatch to
quantify).

CPM production internal consistency: CPM's own canary (`cpm_live.py:295,408`), safe
selector (`best_safe`, `cpm_live.py:374`), and the HAA benchmark (`haa_wf`) all call
the same `sig_13612U`. The memo (lines 77, 95, 107-108, 122-123) describes all of
these as 13612U/unweighted. Internally consistent.

## Verification table: HAA-Balanced (G8/T4) paper spec vs benchmark impl

Benchmark targets HAA-Balanced (the paper's preferred setup, Top4-of-8). `haa_wf`
in `cpm_haa_benchmark_ladder.py` is the standalone canonical impl; `param_wf(...,
all-OFF)` is the factorial's HAA end, gated weight-by-weight equal to `haa_wf`
(`gates.allOFF_eq_canonical_HAA.weight_mismatches = 0`, **pass**).

| HAA paper spec (G8/T4 Balanced) | Implementation | Match? |
|---|---|---|
| Offensive universe 8: SPY, IWM, VEA, VWO, DBC, VNQ, IEF, TLT | `HAA_UNIVERSE = [SPY,IWM,VEA,VWO,VNQ,DBC,IEF,TLT]` (ladder L57) | YES |
| Canary universe: single asset TIP | `tip = sig_13612U(monthly["TIP"])`; risk-off if NaN or `<= 0` | YES |
| Canary rule: risk-on iff TIP 13612U > 0 (else fully defensive) | `if pd.isna(tip) or tip <= 0: return {safe:1.0}` | YES |
| Momentum filter (all universes): 13612U unweighted | `sig_13612U` = `(r1+r3+r6+r12)/4` | YES (see crux) |
| Rank offensive by 13612U, take Top4 (= half of 8) | `ranked = mom.sort_values(desc); top = iloc[:min(4,...)]` (TOP_K=4) | YES |
| Absolute-momentum partial-safe: each Top4 slot with 13612U <= 0 -> defensive asset's 25% tranche | `for t in top: if top[t]>0: out[t]+=0.25 else: out[safe]+=0.25` | YES |
| Defensive universe: best of {BIL, IEF} by 13612U | `best_safe(monthly, sig_d, SAFE)`, `SAFE=["SHV","IEF"]` | YES* (BIL->SHV) |
| Weighting: equal-weight surviving picks, 1/TopX = 25% each | `out[t]+=0.25` per surviving pick | YES |
| Rebalance: monthly, last trading day, hold one month | monthly `resample("ME")`, monthly weight fn | YES |

*Single instrument substitution: paper's defensive cash leg is BIL (1-3m T-Bill);
impl uses SHV (1-12m T-Bill). Both ultra-short Treasury cash proxies. Documented in
the code header as a "cosmetic wash" chosen for longer SHV history. Materiality: low
-- SHV has marginally more duration than BIL, negligible effect on the cash leg in
risk-off months. This is the only deviation, and it is shared by both the HAA
baseline and CPM ends (so it does not bias the HAA-vs-CPM decomposition).

## Other spec points (paper vs impl) -- materiality

| Spec point | Paper | Impl | Deviation / materiality |
|---|---|---|---|
| Top size T | 4 (half of G8) | `TOP_K = 4` | none |
| Partial-safe (breadth) | per-slot replacement to safe | per-slot 0.25->safe (`haa_wf`); breadth-fraction form in `param_wf` (equivalent at equal-weight) | none material |
| Safe selector | argmax 13612U over {BIL,IEF} | argmax 13612U over {SHV,IEF} | low (BIL->SHV) |
| Equal-weight | 25% each | 0.25 each | none |
| Variant benchmarked | HAA-Balanced G8/T4 (paper's preferred) | G8/T4 | correct variant chosen (not the "lucky shot" HAA-Simple SPY-only) |

## Benchmark numbers (mooex T+1, 10bps/side, shared engine), from JSON

| Config | Window | Sharpe | Calmar | MaxDD |
|---|---|---|---|---|
| HAA standalone (`haa_wf`) | CLEAN (2008-05-30..) | 0.8670 | 0.6386 | -14.68% |
| HAA param all-OFF | CLEAN | 0.8670 | 0.6386 | -14.68% |
| HAA standalone | EXT (1999-03..) | 1.0307 | 0.7527 | -14.68% |

Memo headline (cpm_memo.md:308,315): HAA Clean = 0.87 / 0.64 / -14.68%. Confirmed
against JSON. Standalone `haa_wf` and factorial all-OFF agree to 4dp (gate passes),
so the headline HAA peer numbers are reproduced by two independent code paths.

## Verdict

**HAA benchmark is FAITHFUL to the paper.** The feared 13612U-vs-13612W bug does
not exist: HAA's published metric IS the unweighted 13612U, the code computes the
unweighted 13612U, and the memo describes the unweighted 13612U. All three agree;
CPM's production canary/safe selector use the same metric and are internally
consistent with the memo. No correction needed and no impact to quantify.

Only deviation is the BIL->SHV defensive-cash substitution (documented, low
materiality, symmetric across HAA and CPM ends so it does not distort the
mechanism-vs-universe decomposition). The correct paper variant (HAA-Balanced
G8/T4, not the lucky-shot HAA-Simple) is benchmarked. Confidence: high (verbatim
paper recipe + line-cited code + weight-by-weight gate pass + reproduced numbers).

## Evidence index

- Paper recipe: TrendXplorer "Introducing HAA" (Keller collaborator blog),
  SSRN 4346906; AllocateSmartly HAA writeup.
- `cpm_live.py:269-281` (`sig_13612U` unweighted), `:355-376` (`best_safe`),
  `:295,408` (canary uses sig_13612U).
- `research/cpm_haa_benchmark_ladder.py:57` (HAA_UNIVERSE), `:79-112` (`haa_wf`),
  `:gates` allOFF==canonical pass.
- `research/cpm_haa_benchmark_ladder.json` (benchmark metrics + gates).
- `cpm_memo.md:77,95,107-108,122-123,308,315`.

## Candidates

- Memory candidate: None (no methodology defect found).
- Knowledge candidate: HAA uses the UNWEIGHTED 13612U momentum (avg of 1/3/6/12m
  total returns), NOT VAA/DAA's weighted 13612W. CPM's `sig_13612U` and the HAA
  benchmark both compute the unweighted form -> faithful to Keller & Keuning (2023),
  SSRN 4346906. Benchmark = HAA-Balanced G8/T4; only deviation is BIL->SHV cash wash.
