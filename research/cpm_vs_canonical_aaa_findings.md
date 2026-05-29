# CPM vs Canonical AAA -- corrected benchmark + canary component decomposition

Date: 2026-05-30. Role: analyst (read-only, no production change, no commit).
Script: `research/cpm_vs_canonical_aaa.py` -> `research/cpm_vs_canonical_aaa.json`.

> SUPERSEDES the AAA+TIP-anchored CPM numbers in
> `research/sleeve_vs_benchmark_findings.md` and
> `research/factorial_decomposition_findings.md` for the CPM side ONLY.
> BULL / HAA-simple is unchanged (HAA canonically carries the TIP canary).

## Correction summary

Prior work benchmarked the CPM sleeve against "AAA + TIP canary" (`bench_aaa_tip`,
`build_dashboard.py:352`), a non-canonical hybrid. The canonical comparator is
Adaptive Asset Allocation (Butler-Philbrick 2012): momentum (13612U) top-half +
minimum-variance weighting over the AAA cross-asset universe, with NO canary /
NO TIP gate. Defense in canonical AAA comes only from whatever rises to the top
of the momentum ranking (bonds/cash via the positive-momentum screen and the
SHV/IEF best-of-safe fallback).

The canary is therefore a component CPM ADDS, not a shared baseline feature.

### Canonical AAA construction (line removed, verified)

Canonical AAA = repo `bench_aaa_tip` with the TIP canary block deleted. The
removed lines (`build_dashboard.py`, in `bench_aaa_tip`, around 363-366):

```python
tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
if not (pd.notna(tipm) and tipm > 0):
    wh.append((sd, {safe: 1.0})); continue     # <-- TIP canary risk-off gate, REMOVED
```

Everything else is byte-identical to the repo AAA: universe
`["SPY","EFA","EEM","VNQ","GLD","TLT","DBC"]` (`build_dashboard.py:313`), 13612U
ranker, `top_half = ceil(7/2) = 4` cap, positive-momentum screen, SLSQP min-var
over survivors with `tail(504)` cov lookback, SHV/IEF best-of-safe.

If "canonical AAA" is ambiguous: AAA = momentum + min-variance, no canary. That
is what was used.

## Execution convention (all tables)

Headline convention everywhere: realistic T+1 MOO exact (`mooex`), post-cost
10 bps/side, via the shared `_segment_returns_conv` harness (cost/window/
execution byte-identical across CPM, canonical AAA, AAA+TIP, and every canary
cell). The CPM sleeve itself has no vol gate, so no vol gate is applied here.
Windows: CLEAN 18y (2008-05-30 ..), EXT 27y (1999-03-10 ..), end 2026-05-22.

## Anchor sanity (CLEAN 18y, mooex)

| series | Sharpe | Calmar | note |
|---|---|---|---|
| CPM-solo (all-ON, production) | 1.242 | 0.870 | reproduces published ~1.242/0.870 OK |
| CPM prod structure + HYG-OR-TIP canary | 1.242 | 0.870 | cross-check == CPM-solo OK |
| Canonical AAA (all-OFF, no canary) | 0.970 | 0.556 | new CPM-side anchor |

## (1) Corrected headline benchmark: CPM-solo vs canonical AAA (no canary)

Config: CPM production sleeve vs canonical AAA (no canary). mooex, 10 bps/side.

### CLEAN 18y (2008-05-30 ..)

| series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|
| CPM-solo | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| canonical AAA | 0.970 | 11.48% | 12.00% | -20.65% | 0.556 |

Active (CPM minus canonical AAA): dCAGR +2.76pp, dCalmar +0.315, dSharpe +0.273,
dMaxDD +4.30pp (shallower). Return corr 0.827, TE 6.89%, IR +0.343, n=4524.

### EXT 27y (1999-03-10 ..)

| series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|
| CPM-solo | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| canonical AAA | 1.032 | 11.91% | 11.55% | -20.65% | 0.577 |

Active (CPM minus canonical AAA): dCAGR +2.04pp, dCalmar +0.256, dSharpe +0.132,
dMaxDD +3.89pp (shallower). Return corr 0.789, TE 7.60%, IR +0.242, n=6856.

## How canonical AAA (no canary) differs from the old AAA+TIP baseline

Config: AAA universe, identical engine, only difference = TIP canary present/absent.

| window | series | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---|---|---|---|
| CLEAN 18y | canonical AAA | 0.970 | 11.48% | -20.65% | 0.556 |
| CLEAN 18y | AAA+TIP (old) | 1.041 | 10.97% | -20.82% | 0.527 |
| EXT 27y | canonical AAA | 1.032 | 11.91% | -20.65% | 0.577 |
| EXT 27y | AAA+TIP (old) | 1.065 | 10.87% | -20.82% | 0.522 |

Delta canonical minus AAA+TIP: CLEAN dSharpe -0.071, dMaxDD +0.18pp, dCalmar +0.029;
EXT dSharpe -0.033, dMaxDD +0.18pp, dCalmar +0.055.

Note on the prior expectation (deeper MaxDD for canonical since it has no risk-off):
the MaxDD is essentially identical (-20.65% vs -20.82%, +0.18pp). On the diversified
AAA cross-asset universe the canary is nearly inert for drawdown -- the universe
self-defends via bond/cash momentum (TLT/cash rise in the ranking and the positive
screen + best-of-safe already de-risk). Canonical AAA actually has slightly higher
CAGR and Calmar (less time parked in cash), and slightly lower Sharpe (slightly
higher vol). The TIP canary on the AAA universe trades a hair of return for a hair
of vol smoothing; it does NOT add the large risk-off protection it provides in CPM.

## (3) Canary component decomposition

Config: CPM PRODUCTION structure (QQQ/quality universe `["QQQ","SPHQ","EFA","EEM",
"VNQ","GLD","TLT","DBC"]`, vol-adjusted Faber ranker, 50/50 min-var pair), with all
other components at production-on; ONLY the canary input is varied. Baseline = none
(= canonical-AAA-style defense: no risk-off gate). mooex, 10 bps/side.

### CLEAN 18y

| canary | Sharpe | Calmar | MaxDD | CAGR | vs none |
|---|---|---|---|---|---|
| none | 1.022 | 0.364 | -35.27% | 12.85% | -- |
| TIP-only | 1.155 | 0.760 | -16.35% | 12.42% | dSharpe +0.133, dCalmar +0.395, dMaxDD +18.92pp |
| HYG-only | 1.328 | 1.116 | -13.12% | 14.65% | dSharpe +0.306, dCalmar +0.752, dMaxDD +22.15pp |
| HYG-OR-TIP (prod) | 1.242 | 0.870 | -16.35% | 14.23% | dSharpe +0.220, dCalmar +0.506, dMaxDD +18.92pp |

### EXT 27y

| canary | Sharpe | Calmar | MaxDD | CAGR | vs none |
|---|---|---|---|---|---|
| none | 1.047 | 0.375 | -35.59% | 13.36% | -- |
| TIP-only | 1.119 | 0.700 | -16.76% | 11.73% | dSharpe +0.072, dCalmar +0.325, dMaxDD +18.83pp |
| HYG-only | 1.250 | 0.925 | -15.78% | 14.60% | dSharpe +0.203, dCalmar +0.550, dMaxDD +19.80pp |
| HYG-OR-TIP (prod) | 1.164 | 0.832 | -16.76% | 13.95% | dSharpe +0.117, dCalmar +0.457, dMaxDD +18.83pp |

### Which input dominates

HYG (high-yield) drives the canary contribution. On every metric and both windows,
HYG-only is the strongest single input (CLEAN Sharpe 1.328 / Calmar 1.116 /
MaxDD -13.12%; EXT 1.250 / 0.925 / -15.78%) and HYG-OR-TIP sits between TIP-only
and HYG-only. TIP-only is the weakest risk-off input but still cuts the no-canary
-35% drawdown to -16%. This confirms the existing finding: high-yield carries the
effective risk-off signal, while the inflation-protected leg (TIP) is a
breadth/governance leg -- it dilutes raw performance (HYG-OR-TIP < HYG-only) but
adds an independent confirmation that makes the gate more robust/governable.

Key contrast vs the benchmark side: the canary is enormous on the CPM production
universe (none -> HYG-OR-TIP improves MaxDD by ~19pp, -35% to -16%) but nearly
inert on the AAA cross-asset universe (~0.2pp MaxDD). The equity-heavy QQQ/quality
universe needs the explicit risk-off gate; the diversified AAA universe self-defends
via bond momentum.

## New CPM main effect for the canary (component CPM adds)

Because the baseline is now canonical AAA (no canary), the canary effect measures
ADDING a canary vs none, which is much larger than the old TIP -> HYG-OR-TIP swap:

- New "add HYG-OR-TIP canary" effect (production structure, CLEAN): dSharpe +0.220,
  dCalmar +0.506, dMaxDD +18.92pp.
- Old framing (TIP-only -> HYG-OR-TIP swap, CLEAN): dSharpe +0.087, dCalmar +0.110
  (HYG-OR-TIP 1.242/0.870 vs TIP-only 1.155/0.760).

The canary is now the single largest CPM-vs-canonical-AAA improvement component on
this universe; the bulk of its value is the existence of a risk-off gate at all,
and within the gate, HYG is the dominant input.

## Re-derived ladder ordering (canonical-AAA anchor, CLEAN, scoped)

Full 2^4 grid was intentionally NOT re-run (scope). Using the scoped pieces that
change with the corrected anchor, the dominant CPM-vs-canonical-AAA Calmar
contributors order as:

1. Canary (add HYG-OR-TIP, HYG-dominant): dCalmar +0.506 (none -> prod canary, prod structure).
2. Universe + ranker + pairing combined: remaining gap from canonical AAA Calmar
   0.556 to CPM-solo 0.870, net of the canary leg.

The canary moves from a minor swap effect (old anchor) to the headline CPM
component once the baseline has no risk-off gate.

## Caveats / confidence

- Scope intentionally minimal: only the pieces that change with the corrected
  anchor were computed. No full 2^4 factorial; main-effect/interaction tables from
  the old factorial are NOT re-derived here.
- Canary decomposition holds U/R/P at production-on; cross-component interactions
  with the canary are not isolated (would need the full grid).
- All numbers mooex / 10 bps/side / no vol gate (CPM has none). Confidence high on
  the anchors (CPM 1.242/0.870 reproduces exactly; production+HYG-OR-TIP cross-check
  matches CPM-solo exactly), high on the canary-input ordering (consistent across
  both windows).

## Key new numbers

- Canonical AAA anchor (new CPM-side baseline): CLEAN Sharpe 0.970 / Calmar 0.556 /
  MaxDD -20.65%; EXT 1.032 / 0.577 / -20.65%.
- CPM-solo vs canonical AAA (CLEAN): dSharpe +0.273, dCalmar +0.315, dCAGR +2.76pp,
  IR +0.343, corr 0.827.
- New canary main effect (add HYG-OR-TIP, prod structure, CLEAN): dSharpe +0.220,
  dCalmar +0.506, dMaxDD +18.92pp.
- Canary-input winner: HYG-only (CLEAN 1.328 / 1.116 / -13.12%); HYG dominates,
  TIP is the breadth/governance leg.
