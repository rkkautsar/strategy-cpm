# CPM PC1 / absorption-ratio gate -- walk-forward & overfit validation

Role: analyst (hypothesis-driven, READ-ONLY re production; no prod/memo edits; no commit). Throwaway harness `research/cpm_pc1_walkforward.py`.

**Setup:** IV4 production spec; execution T+1 MOO exact (`mooex`); post-cost 10 bps/side; PC1 = dominant-eigenvalue share of rolling daily-return correlation matrix of CPM's 8 risky assets, point-in-time (<= month-end decision), de-risk T+1. Clean 2008-05-30..2026-05-22.

## 0. Anchor + reproduce gate

| Check | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| Prod CPM clean | 1.1910 | -12.67% | 1.0615 | 1.1910/-12.67%/1.0615 | CONFIRMED |
| C3 PC1>70% risky*0.5 (w60) | 1.2144 | -12.67% | 1.0766 | Sharpe~1.2144 | CONFIRMED |

Base (gate-off) self-check Sharpe 1.190980, matches production = True. WF deltas trusted on this basis.

## 1. Threshold response surface (window 60, full clean)

Production (no gate) clean Sharpe **1.1910**, Calmar **1.0615**. Cells = clean Sharpe; **bold** beats prod. floor = risky-exposure multiplier when PC1>thr (floor 0 = full de-risk to safe, 0.5 = half).

| thr \ floor | floor 0 | floor 0.25 | floor 0.5 | floor 0.75 |
|---|---:|---:|---:|---:|
| 60% | 0.9995 | 1.0921 | 1.1551 | 1.1866 |
| 62% | 0.9659 | 1.0591 | 1.1286 | 1.1719 |
| 64% | 1.1059 | 1.1489 | 1.1774 | **1.1911** |
| 66% | 1.0674 | 1.1097 | 1.1447 | 1.1718 |
| 68% | 1.1412 | 1.1612 | 1.1762 | 1.1862 |
| 70% | **1.2276** | **1.2223** | **1.2144** | **1.2040** |
| 72% | **1.1923** | **1.1947** | **1.1953** | **1.1941** |
| 74% | 1.1866 | 1.1883 | 1.1896 | 1.1905 |
| 76% | **1.1947** | **1.1942** | **1.1934** | **1.1923** |
| 78% | 1.1852 | 1.1867 | 1.1882 | 1.1897 |
| 80% | 1.1910 | 1.1910 | 1.1910 | 1.1910 |

Calmar surface:

| thr \ floor | floor 0 | floor 0.25 | floor 0.5 | floor 0.75 |
|---|---:|---:|---:|---:|
| 60% | 0.7001 | 0.8384 | 0.9254 | 0.9945 |
| 62% | 0.6061 | 0.7452 | 0.9164 | 0.9898 |
| 64% | 0.9222 | 0.9587 | 0.9941 | 1.0285 |
| 66% | 0.6483 | 0.9083 | 0.9878 | 1.0250 |
| 68% | 0.9923 | 1.0103 | 1.0278 | 1.0450 |
| 70% | **1.0907** | **1.0838** | **1.0766** | **1.0692** |
| 72% | 1.0587 | 1.0597 | 1.0605 | 1.0611 |
| 74% | 1.0570 | 1.0582 | 1.0594 | 1.0605 |
| 76% | **1.0656** | **1.0646** | **1.0636** | **1.0626** |
| 78% | 1.0558 | 1.0572 | 1.0587 | 1.0602 |
| 80% | 1.0615 | 1.0615 | 1.0615 | 1.0615 |

## 2a. Expanding walk-forward (annual re-selection, OOS)

Each mid-year boundary, select config by best trailing in-sample Sharpe over [2008-05-30..boundary] from candidate set {prod, thr62/66/70/74/78 x floor0/0.5, w60}, apply forward 1y, stitch. OOS span 2011-06-01..2026-05-22 (15 re-selections).

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| WF (OOS-selected) | 1.2726 | 13.49% | 10.32% | -12.67% | 1.0649 | 4.3957 |
| Prod (same OOS span) | 1.2519 | 13.37% | 10.41% | -12.67% | 1.0557 | 4.2493 |

WF delta vs prod-OOS: Sharpe +0.0207, Calmar +0.0093.

Selection frequency: {'thr70_f0': 15}.

Per-boundary selection (selected config | trailing-train Sharpe):

| Boundary | Selected | Train Sharpe |
|---|---|---:|
| 2011-06-01 | thr70_f0 | 1.1177 |
| 2012-06-01 | thr70_f0 | 1.0584 |
| 2013-06-01 | thr70_f0 | 1.0793 |
| 2014-06-01 | thr70_f0 | 1.1087 |
| 2015-06-01 | thr70_f0 | 1.1398 |
| 2016-06-01 | thr70_f0 | 1.1175 |
| 2017-06-01 | thr70_f0 | 1.1513 |
| 2018-06-01 | thr70_f0 | 1.1310 |
| 2019-06-01 | thr70_f0 | 1.0612 |
| 2020-06-01 | thr70_f0 | 1.1100 |
| 2021-06-01 | thr70_f0 | 1.2002 |
| 2022-06-01 | thr70_f0 | 1.1768 |
| 2023-06-01 | thr70_f0 | 1.1227 |
| 2024-06-01 | thr70_f0 | 1.1322 |
| 2025-06-01 | thr70_f0 | 1.1093 |

## 2b. Split-sample (select on train, evaluate on test)

| Split | Selected on train | Test: selected Sharpe | Test: prod Sharpe | Test: fixed thr70/f0.5 |
|---|---|---:|---:|---:|
| train 2008-2016 / test 2017-2026 | thr70_f0 | 1.3753 | 1.3753 | 1.3753 |
| train 2017-2026 / test 2008-2016 | prod | 0.9970 | 0.9970 | 1.0422 |

Train-period in-sample Sharpe by candidate (shows whether the full-sample winner is even best in-sample on each half):

- **train 2008-2016 / test 2017-2026** train ranking: thr70_f0 1.0699, thr70_f0.5 1.0422, prod 0.9970, thr74_f0.5 0.9938, thr78_f0.5 0.9913, thr74_f0 0.9880 ...
- **train 2017-2026 / test 2008-2016** train ranking: prod 1.3753, thr70_f0 1.3753, thr70_f0.5 1.3753, thr74_f0 1.3753, thr74_f0.5 1.3753, thr78_f0 1.3753 ...

## 3. Robustness -- correlation window sensitivity (full clean)

Prod Sharpe 1.1910 / Calmar 1.0615. **bold** beats prod Sharpe.

| config | window | thr | floor | Sharpe | Calmar | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| w40_thr66_f0 | 40 | 66% | 0 | 1.0357 | 0.6216 | -17.81% |
| w40_thr66_f0.5 | 40 | 66% | 0.5 | 1.1315 | 0.9690 | -12.67% |
| w40_thr70_f0 | 40 | 70% | 0 | 1.1631 | 1.0223 | -12.67% |
| w40_thr70_f0.5 | 40 | 70% | 0.5 | 1.1837 | 1.0425 | -12.67% |
| w40_thr74_f0 | 40 | 74% | 0 | **1.1958** | 1.0625 | -12.67% |
| w40_thr74_f0.5 | 40 | 74% | 0.5 | **1.1963** | 1.0625 | -12.67% |
| w60_thr66_f0 | 60 | 66% | 0 | 1.0674 | 0.6483 | -17.81% |
| w60_thr66_f0.5 | 60 | 66% | 0.5 | 1.1447 | 0.9878 | -12.67% |
| w60_thr70_f0 | 60 | 70% | 0 | **1.2276** | 1.0907 | -12.67% |
| w60_thr70_f0.5 | 60 | 70% | 0.5 | **1.2144** | 1.0766 | -12.67% |
| w60_thr74_f0 | 60 | 74% | 0 | 1.1866 | 1.0570 | -12.67% |
| w60_thr74_f0.5 | 60 | 74% | 0.5 | 1.1896 | 1.0594 | -12.67% |
| w90_thr66_f0 | 90 | 66% | 0 | 1.1073 | 0.9615 | -12.67% |
| w90_thr66_f0.5 | 90 | 66% | 0.5 | 1.1605 | 1.0124 | -12.67% |
| w90_thr70_f0 | 90 | 70% | 0 | 1.1649 | 1.0316 | -12.67% |
| w90_thr70_f0.5 | 90 | 70% | 0.5 | 1.1821 | 1.0470 | -12.67% |
| w90_thr74_f0 | 90 | 74% | 0 | 1.1816 | 1.0517 | -12.67% |
| w90_thr74_f0.5 | 90 | 74% | 0.5 | 1.1867 | 1.0568 | -12.67% |

## 3b. Per-year return contribution (C3 thr70/f0.5/w60 vs prod)

Delta = C3 calendar-year return minus prod. n_fires = months PC1>70% fired that year. Shows whether the edge concentrates in one or two high-corr episodes.

| Year | Prod ret | C3 ret | Delta | n_fires |
|---|---:|---:|---:|---:|
| 2008 | 5.08% | 5.08% | +0.00% | 0 |
| 2009 | 14.47% | 14.47% | +0.00% | 0 |
| 2010 | 16.62% | 19.19% | +2.57% | 3 |
| 2011 | 10.44% | 13.41% | +2.97% | 5 |
| 2012 | 6.72% | 4.80% | -1.92% | 1 |
| 2013 | 19.47% | 19.47% | +0.00% | 0 |
| 2014 | 15.78% | 15.78% | +0.00% | 0 |
| 2015 | -0.97% | -0.97% | +0.00% | 0 |
| 2016 | 10.36% | 10.36% | +0.00% | 0 |
| 2017 | 22.43% | 22.43% | +0.00% | 0 |
| 2018 | 1.92% | 1.92% | +0.00% | 0 |
| 2019 | 12.41% | 12.41% | +0.00% | 0 |
| 2020 | 23.43% | 23.43% | +0.00% | 0 |
| 2021 | 26.22% | 26.22% | +0.00% | 0 |
| 2022 | -0.50% | -0.50% | +0.00% | 0 |
| 2023 | 1.60% | 1.60% | +0.00% | 0 |
| 2024 | 15.08% | 15.08% | +0.00% | 0 |
| 2025 | 26.47% | 26.47% | +0.00% | 0 |
| 2026 | 20.84% | 20.84% | +0.00% | 0 |

Sum of yearly deltas: +3.62%. Firing months (clean, w60, PC1>70%): 2010-05-28(0.70), 2010-06-30(0.73), 2010-07-30(0.73), 2011-08-31(0.72), 2011-09-30(0.72), 2011-10-31(0.74), 2011-11-30(0.76), 2011-12-30(0.79), 2012-01-31(0.76).

## 4. Verdict: REJECT (overfit peak / single-episode artifact)

**The C3 edge is in-sample-selected, not real.** Three independent tests converge on the same conclusion, and the per-year decomposition exposes the mechanism.

### Threshold surface = sharp isolated spike, NOT a plateau

On the floor-0 (full de-risk) column the response is: 64%=1.1059, 66%=1.0674, 68%=1.1412, **70%=1.2276**, 72%=1.1923, 74%=1.1866. The 70% cell sits +0.086 above its 68% neighbor and +0.035 above 72%; every other threshold is at-or-near prod (1.1910) or worse. Low thresholds (60-66%) actively HURT (down to 0.97-1.11) because they over-gate. This is a textbook single-cell spike: move the threshold one 2-point step in either direction and the edge collapses to noise. No broad robust plateau exists.

### Window sensitivity = the spike also requires exactly 60d

At thr=70%/floor=0: w40=1.1631, **w60=1.2276**, w90=1.1649 -- both 40d and 90d windows fall BELOW production. The edge needs the precise (window=60, thr=70%) pair; it is doubly fragile (window-specific AND threshold-specific). w40's own best (thr74, 1.1958) and w90's best (~1.187) are within noise of prod. Nothing survives perturbation of the correlation-window length.

### Per-year decomposition = ONE episode drives 100% of the edge

The PC1>70% gate fires in exactly **9 months, ALL in 2010-2012** (eurozone sovereign-debt high-correlation regime). It NEVER fires from 2013 through 2026. The entire +3.62% cumulative return advantage comes from 2010 (+2.57%), 2011 (+2.97%), and 2012 (-1.92%) -- i.e. one high-correlation episode 14+ years ago. From 2013 onward C3 is byte-identical to production.

### Walk-forward / split-sample confirm zero forward value

- **Clean OOS split (train 2008-2016 -> test 2017-2026):** training selects thr70_f0, but on the 2017-2026 test set the gate never fires, so selected == prod == fixed-thr70 == 1.3753. **Zero OOS benefit.**

- **Reverse split (train 2017-2026 -> test 2008-2016):** training selects PROD (the gate is inert and cannot be distinguished from prod in 2017-2026), so you would NOT deploy the gate; the gate *would* have helped in 2008-2016 (fixed-thr70 1.0422 vs prod 0.9970), but that benefit is unreachable from post-2012 data. The signal and its payoff are confined to the same in-sample episode.

- **Expanding WF (+0.0207 Sharpe) is illusory:** WF re-selects thr70_f0 at all 15 boundaries (the 2010-2012 episode dominates every trailing window), and the only OOS pieces where it differs from prod are 2011-2012 -- the tail of the very episode that defines the signal. Post-2012 the WF series equals prod. The WF 'edge' is the same single episode leaking into the early OOS span, not repeatable forward skill.

### Cost/benefit

Even granting the in-sample 1.2144, the overlay adds a rolling correlation-matrix + eigenvalue machinery for a +0.02 Sharpe that (a) is a single-cell spike in (window,threshold) space, (b) delivers ZERO crisis protection (MaxDD identical in every regime; never fires in GFC/COVID/2022/dot-com), and (c) provides ZERO benefit in a clean post-2012 OOS because it never fires. The complexity is unjustified and the apparent edge is an artifact of one 2010-2012 high-correlation episode that happens to fall inside the sample.

### Recommendation: **REJECT.** Do not adopt. Document only as a cautionary overfit example: a 3-point in-sample sweep with a single winner (70%) was, on fine sweep, a literal isolated spike; the 'survives execution lag' check was necessary but not sufficient -- lag-robustness does not protect against single-episode in-sample selection. The discriminating tests were the FINE threshold+window surface and the per-year firing decomposition.

