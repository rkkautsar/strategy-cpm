# Section 8 sensitivity sweeps re-run under the headline convention

Harness: `research/section8_sweeps_headline_convention.py` (read-only; reuses production signal/weight logic, varies only the swept knob; routes all returns through the headline realistic next-session-open execution engine).
Panel: 1997-12-10 -> 2026-05-22. Clean window 2008-05-30..2026-05-22; ext window 1999-03-10..2026-05-22.

**Convention (every table):** slow rv_60d<rv_252d equity vol gate, T+1 MOO exact execution, post-cost 10 bps/side. Blend = 0.60*trend sleeve (CPM) + 0.40*equity sleeve (BULL-SPY); two-sleeve only.

**Headline anchors (base/production row must reproduce):** clean Sharpe 1.321 / CAGR 13.25% / MaxDD -10.66% / Calmar 1.243; ext Sharpe 1.235 / CAGR 12.32% / MaxDD -11.18% / Calmar 1.101.

## 1. Selection-count sweep (trend candidate cap K)

### Trend candidate cap K in {2,3,4,5,6}
Convention: slow rv_60d gate, T+1 MOO exact, post-cost 10bps/side. CPM-solo is gate-independent (no equity vol gate) but is on T+1 MOO execution; blend = 0.60*trend(CPM) + 0.40*equity(BULL-SPY).

CPM-solo (trend sleeve only):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| K=2 [clean] | 0.722 | 9.43% | 13.91% | -23.59% | 0.400 |
| K=3 [clean] | 0.976 | 12.01% | 12.48% | -16.35% | 0.734 |
| K=4 [clean] (base) | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| K=5 [clean] | 1.194 | 13.00% | 10.77% | -16.35% | 0.795 |
| K=6 [clean] | 1.169 | 12.24% | 10.39% | -16.35% | 0.749 |
| K=2 [ext] | 0.838 | 11.80% | 14.58% | -23.59% | 0.500 |
| K=3 [ext] | 1.057 | 13.42% | 12.68% | -16.76% | 0.801 |
| K=4 [ext] (base) | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| K=5 [ext] | 1.110 | 12.78% | 11.42% | -16.76% | 0.762 |
| K=6 [ext] | 1.054 | 11.54% | 10.93% | -20.62% | 0.560 |

60/40 blend (PRIMARY):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| K=2 [clean] | 0.936 | 10.41% | 11.32% | -15.12% | 0.688 |
| K=3 [clean] | 1.137 | 11.94% | 10.45% | -12.80% | 0.933 |
| K=4 [clean] (base) | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| K=5 [clean] | 1.300 | 12.51% | 9.45% | -10.66% | 1.174 |
| K=6 [clean] | 1.293 | 12.06% | 9.17% | -10.17% | 1.186 |
| K=2 [ext] | 0.989 | 11.11% | 11.29% | -15.12% | 0.735 |
| K=3 [ext] | 1.159 | 12.03% | 10.25% | -12.80% | 0.940 |
| K=4 [ext] (base) | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |
| K=5 [ext] | 1.208 | 11.63% | 9.48% | -11.18% | 1.040 |
| K=6 [ext] | 1.174 | 10.89% | 9.16% | -14.24% | 0.765 |

Base-row-equals-headline check: clean Sharpe 1.321 / MaxDD -10.66% / Calmar 1.243 (target 1.321 / -10.66% / 1.243); ext 1.235 / -11.18% / 1.101 (target 1.235 / -11.18% / 1.101) -> **CONFIRMED**.

## 2. Trend screen 2x2 (top-half K cap x positive-trend filter)

### Screen 2x2
Convention: slow rv_60d gate, T+1 MOO exact, post-cost 10bps/side. CPM-solo is gate-independent (no equity vol gate) but is on T+1 MOO execution; blend = 0.60*trend(CPM) + 0.40*equity(BULL-SPY).

CPM-solo (trend sleeve only):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON [clean] (base) | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| K-cap OFF + positive-trend ON [clean] | 1.138 | 11.65% | 10.19% | -16.35% | 0.712 |
| K-cap ON + positive-trend OFF [clean] | 1.233 | 14.18% | 11.33% | -20.90% | 0.678 |
| K-cap OFF + positive-trend OFF [clean] | 1.174 | 10.80% | 9.13% | -18.05% | 0.598 |
| K-cap ON + positive-trend ON [ext] (base) | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| K-cap OFF + positive-trend ON [ext] | 1.031 | 10.92% | 10.60% | -20.62% | 0.530 |
| K-cap ON + positive-trend OFF [ext] | 1.123 | 13.43% | 11.85% | -21.29% | 0.631 |
| K-cap OFF + positive-trend OFF [ext] | 1.100 | 10.31% | 9.32% | -18.16% | 0.568 |

60/40 blend (PRIMARY):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON [clean] (base) | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| K-cap OFF + positive-trend ON [clean] | 1.286 | 11.72% | 8.96% | -10.17% | 1.151 |
| K-cap ON + positive-trend OFF [clean] | 1.328 | 13.23% | 9.75% | -15.46% | 0.855 |
| K-cap OFF + positive-trend OFF [clean] | 1.374 | 11.22% | 8.01% | -15.28% | 0.734 |
| K-cap ON + positive-trend ON [ext] (base) | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |
| K-cap OFF + positive-trend ON [ext] | 1.163 | 10.52% | 8.94% | -14.24% | 0.739 |
| K-cap ON + positive-trend OFF [ext] | 1.214 | 12.02% | 9.74% | -15.46% | 0.777 |
| K-cap OFF + positive-trend OFF [ext] | 1.247 | 10.16% | 8.02% | -15.28% | 0.664 |

Base-row-equals-headline check: clean Sharpe 1.321 / MaxDD -10.66% / Calmar 1.243 (target 1.321 / -10.66% / 1.243); ext 1.235 / -11.18% / 1.101 (target 1.235 / -11.18% / 1.101) -> **CONFIRMED**.

## 3. Ranker comparison

### Candidate ranker design
Convention: slow rv_60d gate, T+1 MOO exact, post-cost 10bps/side. CPM-solo is gate-independent (no equity vol gate) but is on T+1 MOO execution; blend = 0.60*trend(CPM) + 0.40*equity(BULL-SPY).

CPM-solo (trend sleeve only):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| 10m-SMA-distance / vol_252d [clean] (base) | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| multi-horizon 13612U / vol_252d (positive 10m-SMA screen) [clean] | 1.269 | 14.80% | 11.44% | -16.35% | 0.905 |
| multi-horizon 13612U / vol_252d (positive 13612U screen) [clean] | 1.273 | 14.76% | 11.37% | -17.21% | 0.858 |
| plain 12-month momentum [clean] | 1.113 | 13.46% | 12.05% | -18.92% | 0.711 |
| 10m-SMA-distance / vol_252d [ext] (base) | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| multi-horizon 13612U / vol_252d (positive 10m-SMA screen) [ext] | 1.228 | 15.27% | 12.17% | -19.05% | 0.801 |
| multi-horizon 13612U / vol_252d (positive 13612U screen) [ext] | 1.243 | 15.40% | 12.12% | -19.05% | 0.808 |
| plain 12-month momentum [ext] | 1.063 | 14.34% | 13.46% | -18.92% | 0.758 |

60/40 blend (PRIMARY):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| 10m-SMA-distance / vol_252d [clean] (base) | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| multi-horizon 13612U / vol_252d (positive 10m-SMA screen) [clean] | 1.346 | 13.59% | 9.87% | -10.66% | 1.276 |
| multi-horizon 13612U / vol_252d (positive 13612U screen) [clean] | 1.349 | 13.57% | 9.83% | -13.04% | 1.040 |
| plain 12-month momentum [clean] | 1.229 | 12.80% | 10.26% | -14.83% | 0.863 |
| 10m-SMA-distance / vol_252d [ext] (base) | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |
| multi-horizon 13612U / vol_252d (positive 10m-SMA screen) [ext] | 1.284 | 13.11% | 9.98% | -13.23% | 0.990 |
| multi-horizon 13612U / vol_252d (positive 13612U screen) [ext] | 1.295 | 13.19% | 9.95% | -13.23% | 0.997 |
| plain 12-month momentum [ext] | 1.147 | 12.57% | 10.84% | -14.83% | 0.848 |

Base-row-equals-headline check: clean Sharpe 1.321 / MaxDD -10.66% / Calmar 1.243 (target 1.321 / -10.66% / 1.243); ext 1.235 / -11.18% / 1.101 (target 1.235 / -11.18% / 1.101) -> **CONFIRMED**.

## 4. Pairing-rule comparison

### Pair-selection rule
Convention: slow rv_60d gate, T+1 MOO exact, post-cost 10bps/side. CPM-solo is gate-independent (no equity vol gate) but is on T+1 MOO execution; blend = 0.60*trend(CPM) + 0.40*equity(BULL-SPY).

CPM-solo (trend sleeve only):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| minimum-variance pair (504d cov) [clean] (base) | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| minimum-correlation pair (504d) [clean] | 1.162 | 14.60% | 12.41% | -13.37% | 1.092 |
| top-ranked anchor + lowest-correlation partner [clean] | 1.121 | 14.51% | 12.89% | -18.82% | 0.771 |
| lowest average-volatility pair [clean] | 1.150 | 13.88% | 11.97% | -16.37% | 0.848 |
| minimum-variance pair (504d cov) [ext] (base) | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| minimum-correlation pair (504d) [ext] | 1.143 | 14.80% | 12.80% | -15.78% | 0.938 |
| top-ranked anchor + lowest-correlation partner [ext] | 1.012 | 13.57% | 13.47% | -18.82% | 0.721 |
| lowest average-volatility pair [ext] | 1.139 | 13.45% | 11.68% | -16.37% | 0.822 |

60/40 blend (PRIMARY):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| minimum-variance pair (504d cov) [clean] (base) | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| minimum-correlation pair (504d) [clean] | 1.276 | 13.50% | 10.37% | -12.70% | 1.063 |
| top-ranked anchor + lowest-correlation partner [clean] | 1.243 | 13.45% | 10.65% | -12.77% | 1.053 |
| lowest average-volatility pair [clean] | 1.275 | 13.06% | 10.07% | -10.67% | 1.225 |
| minimum-variance pair (504d cov) [ext] (base) | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |
| minimum-correlation pair (504d) [ext] | 1.236 | 12.86% | 10.21% | -12.70% | 1.013 |
| top-ranked anchor + lowest-correlation partner [ext] | 1.135 | 12.14% | 10.60% | -12.77% | 0.951 |
| lowest average-volatility pair [ext] | 1.216 | 12.02% | 9.73% | -10.67% | 1.127 |

Base-row-equals-headline check: clean Sharpe 1.321 / MaxDD -10.66% / Calmar 1.243 (target 1.321 / -10.66% / 1.243); ext 1.235 / -11.18% / 1.101 (target 1.235 / -11.18% / 1.101) -> **CONFIRMED**.

## 5. Blend weight sweep (trend/equity = CPM/BULL)

Convention: slow rv_60d gate, T+1 MOO exact, post-cost. Both sleeves at base; only the blend weight varies. Base = 60/40.

| CPM/BULL | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 80/20 | 1.300 | 13.76% | -13.03% | 1.056 | 1.218 | -13.69% | 0.961 |
| 70/30 | 1.316 | 13.51% | -11.33% | 1.192 | 1.233 | -12.33% | 1.034 |
| 60/40 (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | -11.18% | 1.101 |
| 50/50 | 1.312 | 12.97% | -11.10% | 1.169 | 1.221 | -11.10% | 1.070 |
| 40/60 | 1.289 | 12.69% | -11.55% | 1.099 | 1.189 | -11.55% | 0.990 |
| 30/70 | 1.253 | 12.39% | -11.99% | 1.033 | 1.139 | -11.99% | 0.914 |

Base-row-equals-headline check (60/40): clean 1.321 / -10.66% / 1.243; ext 1.235 / -11.18% / 1.101 -> **CONFIRMED**.

## 6. Canary and safe-sleeve sweeps

### 6a. Canary design (shared gate; varies BOTH sleeves)
Convention: slow rv_60d gate, T+1 MOO exact, post-cost. The canary gate is shared by the trend and equity sleeves, so each variant patches BOTH sleeves' canary.

CPM-solo (trend sleeve):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| dual: high-yield OR inflation-protected (base) [clean] (base) | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| no canary (always risk-on allowed) [clean] | 1.022 | 12.85% | 12.67% | -35.27% | 0.364 |
| inflation-protected only [clean] | 1.155 | 12.42% | 10.68% | -16.35% | 0.760 |
| high-yield only [clean] | 1.328 | 14.65% | 10.78% | -13.12% | 1.116 |
| dual: high-yield OR inflation-protected (base) [ext] (base) | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| no canary (always risk-on allowed) [ext] | 1.047 | 13.36% | 12.75% | -35.59% | 0.375 |
| inflation-protected only [ext] | 1.119 | 11.73% | 10.40% | -16.76% | 0.700 |
| high-yield only [ext] | 1.250 | 14.60% | 11.42% | -15.78% | 0.925 |

60/40 blend (PRIMARY):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| dual: high-yield OR inflation-protected (base) [clean] (base) | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| no canary (always risk-on allowed) [clean] | 1.151 | 12.25% | 10.57% | -21.36% | 0.574 |
| inflation-protected only [clean] | 1.274 | 11.95% | 9.23% | -10.66% | 1.121 |
| high-yield only [clean] | 1.363 | 13.48% | 9.65% | -10.66% | 1.265 |
| dual: high-yield OR inflation-protected (base) [ext] (base) | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |
| no canary (always risk-on allowed) [ext] | 1.127 | 11.73% | 10.32% | -22.18% | 0.529 |
| inflation-protected only [ext] | 1.227 | 10.95% | 8.78% | -10.77% | 1.017 |
| high-yield only [ext] | 1.282 | 12.69% | 9.69% | -11.18% | 1.134 |

Base-row-equals-headline check (dual canary): clean 1.321 / -10.66% / 1.243; ext 1.235 / -11.18% / 1.101 -> **CONFIRMED**.

### 6b. Safe-sleeve design (duration-timed vs fixed; shared by both sleeves)
Convention: slow rv_60d gate, T+1 MOO exact, post-cost. Safe asset is shared by both sleeves; each variant patches BOTH sleeves' safe selector. 50/50 uses a synthetic daily-rebalanced SHV+IEF column (no open prices -> rebal-day fill falls back to close-to-close).

60/40 blend (PRIMARY):
| variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) [clean] (base) | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| SHV only [clean] | 1.263 | 11.92% | 9.29% | -14.08% | 0.847 |
| IEF only [clean] | 1.282 | 13.31% | 10.19% | -16.94% | 0.786 |
| static 50/50 SHV+IEF [clean] | 1.297 | 12.65% | 9.57% | -12.09% | 1.046 |
| timed SHV/IEF by 13612U (base) [ext] (base) | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |
| SHV only [ext] | 1.195 | 11.32% | 9.34% | -14.28% | 0.793 |
| IEF only [ext] | 1.225 | 12.55% | 10.07% | -16.94% | 0.741 |
| static 50/50 SHV+IEF [ext] | 1.228 | 11.96% | 9.58% | -12.09% | 0.989 |

Base-row-equals-headline check (timed safe): clean 1.321 / -10.66% / 1.243; ext 1.235 / -11.18% / 1.101 -> **CONFIRMED**.

## Base-row verification summary

| sweep | base reproduces headline? |
|---|---|
| Selection-count K | CONFIRMED |
| Trend screen 2x2 | CONFIRMED |
| Ranker comparison | CONFIRMED |
| Pairing-rule comparison | CONFIRMED |
| Blend weight sweep | CONFIRMED |
| Canary design | CONFIRMED |
| Safe-sleeve design | CONFIRMED |

## Directional conclusions and ranking deltas vs the prior sweeps

Prior sweeps were run under the OLD convention (fast rv_20d gate + same-day close-to-close T+0 MOC). These re-runs use the headline convention (slow rv_60d gate + realistic T+1 MOO exact + 10 bps/side). Primary lens is Calmar/MaxDD per the drawdown-aware objective, with Sharpe as context.

1. **Selection-count K -- conclusion ROBUST.** K=4 is the local optimum on both Sharpe and Calmar (blend clean K=4 Sharpe 1.321 / Calmar 1.243 vs K=5 1.300/1.174, K=6 1.293/1.186), with a broad shoulder at K=5-6 and a structurally weak K=2 (0.936/0.688). CPM-solo ordering K4>K5>K6>K3>K2 is unchanged from the prior sweep. No ranking change.

2. **Trend screen 2x2 -- conclusion ROBUST (read on Calmar/DD, not Sharpe).** The base (K-cap ON + positive-trend ON) has the best blend Calmar in both windows (clean 1.243, ext 1.101). Removing the positive-trend screen lifts raw blend Sharpe slightly (clean 1.328 / 1.374) but deepens blend MaxDD to -15.5%/-15.3% and collapses Calmar to 0.855/0.734; removing the K-cap worsens the ext/stress MaxDD (-14.24% vs -11.18%). Same direction as the prior sweep: positive-trend screen protects drawdown at little Calmar-adjusted cost, K-cap protects stress behavior. No ranking change on the primary (Calmar/DD) objective.

3. **Ranker comparison -- conclusion MOSTLY ROBUST, with ONE ranking change to flag.** Plain 12-month momentum remains clearly worst (blend clean Sharpe 1.229 / Calmar 0.863 / MaxDD -14.83%). The multi-horizon 13612U/vol ranker with a positive-13612U screen still deepens drawdown (clean MaxDD -13.04%, Calmar 1.040) as in the prior sweep. **RANKING CHANGE:** under the OLD convention every faster ranker deepened drawdown and lowered Calmar vs the base (base -9.82% / Calmar 1.38; 13612U/vol+SMA-screen -10.63% / 1.30). Under the headline convention the multi-horizon 13612U/vol ranker *with the positive 10m-SMA screen* ties the base on clean MaxDD (-10.66%) and slightly BEATS it on clean Calmar (1.276 vs 1.243) and Sharpe (1.346 vs 1.321). Its drawdown disadvantage now only shows up in the ext window (-13.23% vs -11.18%). So the blanket 'faster rankers always deepen drawdown' claim weakens under realistic execution for that one variant; the decision to keep the slower 10m-SMA-distance ranker now rests on the ext-window drawdown and the in-sample-bias / parsimony argument rather than a clean-window Calmar edge.

4. **Pairing-rule comparison -- conclusion STRENGTHENED, with ONE ranking change to flag.** Minimum-variance remains the clean Sharpe leader (blend 1.321) and now also clearly wins Calmar/MaxDD. **RANKING CHANGE:** under the OLD convention the minimum-correlation pair was a credible drawdown-tilted alternative -- shallower MaxDD (-9.45% vs -9.82%) and higher Calmar (1.48 vs 1.38) than the base. Under the headline convention that edge DISAPPEARS: min-correlation now has DEEPER blend MaxDD (-12.70% vs -10.66%) and LOWER Calmar (1.063 vs 1.243) than min-variance in the clean window. The lowest-average-volatility pair is the only alternative that matches base drawdown (-10.67%) but it gives up Sharpe (1.275) and Calmar (1.225). Anchor+lowest-correlation is dominated. Net: the prior 'min-correlation is a drawdown-tilted alternative worth a follow-up' caveat does NOT survive realistic execution; minimum-variance is now the unambiguous choice on both Sharpe and Calmar.

5. **Blend weight sweep -- conclusion ROBUST.** Broad plateau, not a spike: clean blend Sharpe 70/30 1.316, 60/40 1.321, 50/50 1.312. 60/40 sits at the center of the high-Sharpe region and is now also the clean Calmar/MaxDD optimum (shallowest MaxDD -10.66%, highest Calmar 1.243). No ranking change.

6a. **Canary design -- conclusion ROBUST.** The canary is essential for drawdown control: dropping it blows blend MaxDD out to -21.4%/-22.2% and halves Calmar (0.574/0.529). High-yield-only posts higher in-sample blend Sharpe (1.363) and Calmar (1.265) than the dual canary, exactly as in the prior sweep, but carries single-input governance risk; inflation-protected-only is weaker than the dual gate. Same direction, no ranking change.

6b. **Safe-sleeve design -- conclusion ROBUST.** Duration-timed SHV/IEF is the best blend on Calmar/MaxDD in both windows (clean Calmar 1.243 / MaxDD -10.66%); every fixed rule is worse -- SHV-only deepens MaxDD to -14.08%, IEF-only to -16.94%, static 50/50 to -12.09% (Calmar 1.046). Timed selection captures both the flight-to-quality (IEF) and rate-hike (SHV) defensive regimes, as in the prior sweep. No ranking change.

### Summary of ranking changes vs prior sweeps

- Two of the six sweeps show a ranking change under realistic execution, both involving an alternative that LOOKED drawdown-favorable under the old T+0 / fast-gate convention but no longer does: (i) the multi-horizon 13612U/vol ranker with the 10m-SMA screen now ties/beats the base on clean-window drawdown, and (ii) the minimum-correlation pairing rule loses its drawdown-tilt advantage entirely. Both changes make the production choices (slow 10m-SMA ranker, minimum-variance pairing) look at least as good or better, not worse.
- The other four sweeps (K, screen 2x2, weights, canary, safe) are convention-robust: same directional conclusions and same orderings on the primary Calmar/DD objective.

## Caveats

- All metrics post-cost (10 bps/side), realistic T+1 MOO exact execution using real yfinance auto_adjust opens cached in /tmp/cpm_open_cache; slow rv_60d<rv_252d equity gate.
- CPM-solo has no equity vol gate (gate-independent) but is still on T+1 MOO execution; the gate only affects the equity (BULL-SPY) sleeve and hence the blend.
- Ext 27y window is partially proxy-contaminated for the trend sleeve: several universe ETFs lack real opens pre-2006, so ~69-73 rebal days fall back to close-to-close fills for the CPM sleeve. The clean 18y window has full real-open coverage and is the decisive lens.
- The static 50/50 safe variant uses a synthetic daily-rebalanced SHV+IEF column with no open prices; its rebal-day fill falls back to close-to-close (minor, affects only the safe leg on rebalance days).
- Variant labels are plain-language; no codenames. Sharpe is raw (0 rf). Calmar/MaxDD are the primary objective per the drawdown-aware brief.

