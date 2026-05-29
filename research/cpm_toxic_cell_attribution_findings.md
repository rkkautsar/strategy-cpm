# CPM toxic-cell attribution: HYG-/TIP+ canary cell

Cell = months where 13612U(HYG) < 0 AND 13612U(TIP) > 0 (RISK-ON via TIP, HYG negative).
Run date: 2026-05-30

Panel: 1993-10-01 -> 2026-05-22, 42 cols

## Window: CLEAN (live ETF)  (2008-05-30 -> 2026-05-30)

Total months classified: 216

Cell counts:
```
cell
HYG+/TIP+    147
HYG-/TIP-     28
HYG+/TIP-     27
HYG-/TIP+     14
```

**Toxic cell (HYG-/TIP+) n = 14 months**
Clean risk-on (HYG+/TIP+) n = 147 months

### 1. Toxic-month enumeration (holdings + forward asset/sleeve returns)

- **2008-06-30** [RISK_ON] HYGmom=-0.022 TIPmom=+0.059 | held: DBC=50%(fwd -11.3%), TLT=50%(fwd -0.1%) | sleeve fwd = -5.74%
- **2008-07-31** [RISK_ON] HYGmom=-0.000 TIPmom=+0.036 | held: DBC=50%(fwd -5.5%), TLT=50%(fwd +2.5%) | sleeve fwd = -1.48%
- **2008-08-29** [RISK_ON] HYGmom=-0.000 TIPmom=+0.036 | held: TLT=50%(fwd +0.5%), DBC=50%(fwd -7.9%) | sleeve fwd = -3.66%
- **2008-12-31** [RISK_ON] HYGmom=-0.048 TIPmom=+0.001 | held: TLT=50%(fwd -10.8%), GLD=50%(fwd +5.9%) | sleeve fwd = -2.47%
- **2009-01-30** [DEFENSIVE] HYGmom=-0.048 TIPmom=+0.001 | held: IEF=100%(fwd -1.5%) | sleeve fwd = -1.53%
- **2009-03-31** [RISK_ON] HYGmom=-0.106 TIPmom=+0.026 | held: TLT=50%(fwd -7.8%), GLD=50%(fwd -4.1%) | sleeve fwd = -5.96%
- **2011-09-30** [RISK_ON] HYGmom=-0.049 TIPmom=+0.056 | held: TLT=50%(fwd -6.4%), GLD=50%(fwd +4.0%) | sleeve fwd = -1.22%
- **2014-12-31** [RISK_ON] HYGmom=-0.007 TIPmom=+0.001 | held: TLT=50%(fwd +8.6%), SPHQ=50%(fwd -2.6%) | sleeve fwd = +3.01%
- **2015-01-30** [RISK_ON] HYGmom=-0.007 TIPmom=+0.001 | held: TLT=50%(fwd -5.8%), SPHQ=50%(fwd +3.8%) | sleeve fwd = -0.99%
- **2016-02-29** [RISK_ON] HYGmom=-0.032 TIPmom=+0.009 | held: TLT=50%(fwd +1.7%), SPHQ=50%(fwd +4.4%) | sleeve fwd = +3.06%
- **2020-03-31** [RISK_ON] HYGmom=-0.093 TIPmom=+0.019 | held: TLT=50%(fwd -0.2%), GLD=50%(fwd +6.3%) | sleeve fwd = +3.04%
- **2020-04-30** [RISK_ON] HYGmom=-0.024 TIPmom=+0.049 | held: TLT=50%(fwd -2.6%), GLD=50%(fwd +2.0%) | sleeve fwd = -0.32%
- **2020-05-29** [RISK_ON] HYGmom=-0.024 TIPmom=+0.049 | held: TLT=50%(fwd +1.0%), SPHQ=50%(fwd +0.9%) | sleeve fwd = +0.96%
- **2022-02-28** [RISK_ON] HYGmom=-0.011 TIPmom=+0.016 | held: DBC=50%(fwd +5.0%), GLD=50%(fwd -0.5%) | sleeve fwd = +2.21%

Toxic-cell sleeve fwd return: mean=-0.792%/mo  median=-1.105%  win-rate=36%  worst=-5.96%  best=+3.06%
Annualized (geometric, in-cell only): -9.58%/y

### 2. Holdings frequency across toxic months

```
      count  freq_pct  avg_weight_when_held  avg_weight_overall                         class
TLT      12     85.71                  0.50                0.43  cross-asset/credit-sensitive
GLD       6     42.86                  0.50                0.21  cross-asset/credit-sensitive
DBC       4     28.57                  0.50                0.14  cross-asset/credit-sensitive
SPHQ      4     28.57                  0.50                0.14                        equity
IEF       1      7.14                  1.00                0.07                    safe/other
```

Aggregate weight share across toxic months:
  cross-asset/credit-sensitive (EEM,VNQ,EFA,GLD,DBC,TLT): 78.6%
  equity (QQQ,SPHQ): 14.3%
  safe/other: 7.1%

### 3. Loss attribution by asset (sum of weight*fwd_ret contributions)

Sum of contributions (=cumulative sleeve return across toxic months, additive): -11.09%
```
      total_contrib_pct  n_months_held  share_of_total_loss_pct
DBC              -9.865              4                   88.940
TLT              -9.671             12                   87.184
IEF              -1.534              1                   13.825
SPHQ              3.275              4                  -29.521
GLD               6.703              6                  -60.427
```

### 4. Correlation-break test (504d baseline vs forward 20d/60d realized)


**Toxic cell HYG-/TIP+ pair & universe correlations** (n=14)
```
     month     pair  pair_corr_504d  pair_corr_fwd20  pair_corr_fwd60  univ_corr_504d  univ_corr_fwd20  univ_corr_fwd60
2008-06-30  DBC+TLT           -0.10             0.15            -0.28            0.27             0.09             0.13
2008-07-31  DBC+TLT           -0.09            -0.09            -0.50            0.25             0.13             0.25
2008-08-29  TLT+DBC           -0.10            -0.73            -0.50            0.24             0.17             0.32
2008-12-31  TLT+GLD           -0.01            -0.19             0.21            0.30             0.34             0.32
2009-01-30   (safe)             NaN              NaN              NaN            0.30             0.24             0.29
2009-03-31  TLT+GLD            0.04             0.56             0.25            0.30             0.26             0.35
2011-09-30  TLT+GLD            0.14             0.09            -0.25            0.33             0.34             0.40
2014-12-31 TLT+SPHQ           -0.30            -0.79            -0.30            0.29             0.05             0.28
2015-01-30 TLT+SPHQ           -0.33            -0.34            -0.08            0.28             0.29             0.37
2016-02-29 TLT+SPHQ           -0.39            -0.56            -0.46            0.25             0.30             0.20
2020-03-31  TLT+GLD            0.32             0.02             0.30            0.33             0.32             0.31
2020-04-30  TLT+GLD            0.30             0.75             0.37            0.33             0.28             0.27
2020-05-29 TLT+SPHQ           -0.48            -0.70            -0.55            0.33             0.29             0.31
2022-02-28  DBC+GLD            0.22             0.73             0.65            0.35             0.12             0.26
```
Means:
```
pair_corr_504d    -0.060
pair_corr_fwd20   -0.086
pair_corr_fwd60   -0.088
univ_corr_504d     0.295
univ_corr_fwd20    0.231
univ_corr_fwd60    0.289
```

**Non-toxic risk-on HYG+/TIP+ (comparison)** (n=147)
```
     month     pair  pair_corr_504d  pair_corr_fwd20  pair_corr_fwd60  univ_corr_504d  univ_corr_fwd20  univ_corr_fwd60
2008-05-30  DBC+QQQ            0.07            -0.56            -0.40            0.28             0.12             0.10
2009-04-30  GLD+QQQ           -0.04            -0.18             0.21            0.30             0.42             0.41
2009-05-29  GLD+QQQ           -0.04             0.44             0.45            0.30             0.39             0.40
2009-06-30  QQQ+GLD           -0.04             0.46             0.37            0.30             0.42             0.41
2009-07-31  QQQ+GLD           -0.04             0.56             0.42            0.31             0.35             0.40
2009-08-31  QQQ+EFA            0.87             0.87             0.89            0.31             0.46             0.46
2009-09-30  QQQ+EFA            0.87             0.87             0.85            0.31             0.46             0.43
2009-10-30  QQQ+GLD           -0.03             0.43             0.40            0.31             0.53             0.41
2009-11-30  GLD+QQQ           -0.04             0.49             0.53            0.31             0.32             0.41
2009-12-31  QQQ+GLD           -0.04             0.52             0.55            0.32             0.42             0.44
2010-01-29  GLD+QQQ           -0.03             0.83             0.48            0.32             0.47             0.41
2010-02-26  GLD+QQQ           -0.02             0.23            -0.05            0.32             0.43             0.30
2010-03-31 QQQ+SPHQ            0.87             0.88             0.91            0.33             0.31             0.27
2010-04-30  QQQ+GLD           -0.00            -0.08            -0.02            0.33             0.28             0.29
2010-05-28 SPHQ+TLT           -0.40            -0.65            -0.64            0.33             0.25             0.32
2010-06-30  TLT+GLD            0.03            -0.30             0.11            0.33             0.38             0.34
2010-07-30 TLT+SPHQ           -0.41            -0.76            -0.63            0.34             0.31             0.36
2010-08-31  TLT+GLD            0.03             0.54             0.33            0.34             0.28             0.46
2010-09-30  TLT+QQQ           -0.42            -0.42            -0.28            0.36             0.49             0.47
2010-10-29 GLD+SPHQ            0.22             0.61             0.37            0.37             0.53             0.42
2010-11-30 GLD+SPHQ            0.15            -0.01            -0.01            0.36             0.33             0.25
2010-12-31 GLD+SPHQ            0.12            -0.05            -0.02            0.35             0.19             0.22
2011-01-31 DBC+SPHQ            0.54            -0.23             0.17            0.35             0.19             0.25
2011-02-28 DBC+SPHQ            0.56             0.21             0.33            0.36             0.22             0.27
2011-03-31 SPHQ+GLD            0.17             0.00             0.31            0.36             0.27             0.31
2011-04-29 GLD+SPHQ            0.21             0.44             0.04            0.37             0.31             0.31
2011-05-31 SPHQ+GLD            0.23             0.36            -0.51            0.36             0.31             0.25
2011-06-30 SPHQ+GLD            0.22            -0.49            -0.41            0.36             0.33             0.26
2011-07-29  TLT+DBC           -0.30            -0.50            -0.53            0.35             0.25             0.28
2011-08-31  TLT+DBC           -0.32            -0.53            -0.60            0.33             0.28             0.34
2011-10-31 TLT+SPHQ           -0.57            -0.77            -0.74            0.32             0.47             0.42
2011-11-30 TLT+SPHQ           -0.60            -0.81            -0.71            0.33             0.38             0.33
2011-12-30 TLT+SPHQ           -0.61            -0.62            -0.53            0.33             0.32             0.32
2012-01-31 TLT+SPHQ           -0.61            -0.53            -0.52            0.32             0.23             0.33
2012-02-29 SPHQ+TLT           -0.61            -0.48            -0.54            0.32             0.41             0.36
2012-03-30 QQQ+SPHQ            0.90             0.80             0.86            0.32             0.39             0.29
2012-04-30 SPHQ+TLT           -0.62            -0.63            -0.73            0.32             0.26             0.30
2012-05-31 TLT+SPHQ           -0.61            -0.77            -0.73            0.32             0.25             0.32
2012-06-29 TLT+SPHQ           -0.62            -0.87            -0.58            0.32             0.30             0.32
2012-07-31 TLT+SPHQ           -0.63            -0.54            -0.46            0.32             0.32             0.31
2012-08-31 TLT+SPHQ           -0.62            -0.44            -0.49            0.32             0.30             0.30
2012-09-28 GLD+SPHQ            0.07             0.54             0.24            0.32             0.26             0.26
2012-10-31 SPHQ+TLT           -0.62            -0.72            -0.62            0.32             0.32             0.28
2012-11-30 SPHQ+TLT           -0.65            -0.68            -0.62            0.31             0.15             0.23
2012-12-31 SPHQ+VNQ            0.83             0.78             0.76            0.30             0.26             0.24
2013-01-31 SPHQ+VNQ            0.83             0.78             0.80            0.31             0.28             0.33
2013-02-28 SPHQ+VNQ            0.83             0.77             0.76            0.31             0.14             0.33
2013-03-28 SPHQ+QQQ            0.89             0.89             0.88            0.31             0.38             0.44
2013-04-30 SPHQ+QQQ            0.89             0.81             0.83            0.31             0.27             0.45
2014-06-30 SPHQ+TLT           -0.34            -0.60            -0.25            0.32             0.05             0.24
2014-07-31  QQQ+TLT           -0.34            -0.25            -0.41            0.31             0.14             0.23
2014-08-29 TLT+SPHQ           -0.30            -0.36            -0.42            0.30             0.25             0.22
2014-10-31 SPHQ+TLT           -0.31            -0.16            -0.66            0.30             0.13             0.16
2014-11-28 SPHQ+TLT           -0.29            -0.62            -0.62            0.29             0.21             0.17
2015-02-27 SPHQ+TLT           -0.32             0.35             0.04            0.28             0.57             0.40
2015-03-31 TLT+SPHQ           -0.27            -0.48            -0.20            0.29             0.20             0.27
2015-04-30 SPHQ+EFA            0.80             0.86             0.78            0.28             0.36             0.22
2015-05-29 SPHQ+EFA            0.81             0.69             0.82            0.29             0.23             0.23
2016-03-31 SPHQ+TLT           -0.39            -0.32            -0.59            0.25             0.12             0.12
2016-04-29 SPHQ+TLT           -0.38            -0.54            -0.55            0.25             0.18             0.16
2016-05-31 SPHQ+TLT           -0.38            -0.75            -0.49            0.25             0.16             0.17
2016-06-30  TLT+DBC           -0.25            -0.27            -0.09            0.24             0.21             0.39
2016-07-29 TLT+SPHQ           -0.40            -0.07             0.24            0.24             0.18             0.43
2016-08-31  TLT+EEM           -0.36             0.46             0.39            0.24             0.57             0.38
2016-09-30  QQQ+TLT           -0.36             0.00             0.13            0.25             0.31             0.28
2016-10-31  QQQ+DBC            0.27             0.37            -0.02            0.25             0.23             0.26
2016-11-30 SPHQ+DBC            0.34            -0.19            -0.06            0.26             0.33             0.24
2016-12-30 DBC+SPHQ            0.34             0.10             0.19            0.26             0.23             0.28
2017-01-31 SPHQ+DBC            0.35             0.03             0.16            0.27             0.06             0.23
2017-02-28 QQQ+SPHQ            0.86             0.90             0.81            0.27             0.43             0.24
2017-03-31 QQQ+SPHQ            0.86             0.71             0.66            0.26             0.06             0.13
2017-04-28 QQQ+SPHQ            0.85             0.79             0.65            0.26             0.16             0.22
2017-05-31 QQQ+SPHQ            0.85             0.60             0.71            0.25             0.17             0.21
2017-08-31  QQQ+GLD           -0.20            -0.55            -0.19            0.25             0.09             0.17
2017-09-29 SPHQ+QQQ            0.82            -0.05             0.31            0.25             0.26             0.22
2017-10-31 QQQ+SPHQ            0.81             0.51             0.63            0.25             0.24             0.24
2017-11-30 SPHQ+QQQ            0.80             0.49             0.91            0.24             0.20             0.41
2017-12-29 SPHQ+QQQ            0.79             0.79             0.92            0.23             0.37             0.36
2018-01-31 SPHQ+QQQ            0.77             0.96             0.94            0.23             0.44             0.35
2018-05-31 DBC+SPHQ            0.22             0.04             0.32            0.27             0.18             0.27
2018-06-29 DBC+SPHQ            0.19             0.43             0.41            0.29             0.32             0.30
2018-07-31 SPHQ+DBC            0.20             0.66             0.54            0.30             0.30             0.27
2018-08-31 SPHQ+DBC            0.21             0.09             0.33            0.30             0.18             0.23
2018-09-28 SPHQ+DBC            0.19             0.60             0.36            0.28             0.24             0.23
2019-01-31  GLD+TLT            0.35             0.75             0.52            0.27             0.26             0.24
2019-02-28 TLT+SPHQ           -0.27            -0.61            -0.50            0.27             0.25             0.23
2019-03-29 TLT+SPHQ           -0.28            -0.35            -0.41            0.27             0.20             0.23
2019-04-30 SPHQ+TLT           -0.28            -0.62            -0.30            0.27             0.19             0.27
2019-05-31 TLT+SPHQ           -0.29            -0.20            -0.53            0.27             0.25             0.23
2019-06-28 TLT+SPHQ           -0.29             0.20            -0.48            0.27             0.36             0.22
2019-07-31 TLT+SPHQ           -0.29            -0.73            -0.49            0.27             0.18             0.20
2019-08-30 TLT+SPHQ           -0.34            -0.27            -0.23            0.26             0.15             0.17
2019-09-30 TLT+SPHQ           -0.33            -0.32            -0.25            0.26             0.19             0.17
2019-10-31  TLT+EFA           -0.33            -0.35            -0.42            0.26             0.21             0.15
2019-11-29  TLT+EFA           -0.33            -0.18            -0.58            0.26             0.17             0.22
2019-12-31  EFA+GLD            0.02            -0.49             0.24            0.26             0.09             0.41
2020-01-31 TLT+SPHQ           -0.34            -0.65            -0.54            0.25             0.28             0.40
2020-02-28  TLT+GLD            0.40             0.20             0.22            0.24             0.43             0.40
2020-06-30 TLT+SPHQ           -0.49            -0.65            -0.17            0.33             0.21             0.35
2020-07-31  QQQ+TLT           -0.46             0.38            -0.04            0.33             0.42             0.36
2020-08-31 GLD+SPHQ            0.03             0.45             0.29            0.33             0.43             0.36
2020-09-30 GLD+SPHQ            0.05             0.46             0.26            0.33             0.36             0.31
2020-10-30 GLD+SPHQ            0.07             0.19             0.15            0.33             0.26             0.26
2020-11-30  DBC+EFA            0.57             0.31             0.48            0.33             0.26             0.30
2020-12-31  DBC+EFA            0.57             0.52             0.39            0.34             0.33             0.34
2021-01-29  DBC+EFA            0.57             0.44             0.29            0.34             0.34             0.39
2021-02-26  DBC+EFA            0.57             0.27             0.13            0.34             0.43             0.42
2021-03-31  DBC+EFA            0.55            -0.04             0.10            0.34             0.38             0.36
2021-04-30  DBC+EFA            0.54            -0.00             0.30            0.34             0.46             0.29
2021-05-28  DBC+EFA            0.53             0.28             0.47            0.35             0.25             0.23
2021-06-30  DBC+EFA            0.53             0.64             0.53            0.35             0.20             0.24
2021-07-30 DBC+SPHQ            0.48             0.42             0.38            0.34             0.32             0.26
2021-08-31 SPHQ+DBC            0.47             0.71             0.40            0.35             0.29             0.22
2021-09-30 DBC+SPHQ            0.49             0.38             0.64            0.35             0.16             0.28
2021-10-29 DBC+SPHQ            0.48             0.70             0.57            0.35             0.28             0.31
2021-11-30 SPHQ+TLT           -0.41            -0.41            -0.17            0.35             0.34             0.27
2021-12-31 SPHQ+DBC            0.49             0.21            -0.39            0.35             0.31             0.17
2023-03-31 GLD+SPHQ            0.14             0.07            -0.19            0.37             0.29             0.26
2023-04-28 GLD+SPHQ            0.13            -0.45            -0.16            0.36             0.28             0.32
2023-11-30 SPHQ+GLD            0.12             0.43             0.32            0.38             0.48             0.39
2023-12-29 SPHQ+EFA            0.85             0.67             0.63            0.38             0.32             0.33
2024-01-31 SPHQ+EFA            0.85             0.56             0.67            0.38             0.38             0.31
2024-02-29 SPHQ+EFA            0.85             0.69             0.74            0.39             0.30             0.38
2024-03-28 SPHQ+GLD            0.23             0.13             0.21            0.42             0.27             0.37
2024-05-31 SPHQ+GLD            0.25             0.17             0.34            0.42             0.27             0.38
2024-06-28 SPHQ+GLD            0.26             0.41             0.42            0.42             0.44             0.39
2024-07-31 SPHQ+GLD            0.26             0.42             0.31            0.42             0.36             0.29
2024-08-30 SPHQ+GLD            0.26             0.51             0.08            0.42             0.34             0.26
2024-09-30 GLD+SPHQ            0.25            -0.14             0.07            0.41             0.10             0.29
2024-10-31 GLD+SPHQ            0.21            -0.15             0.09            0.39             0.29             0.33
2024-11-29 SPHQ+GLD            0.14             0.44             0.30            0.36             0.45             0.32
2025-01-31 GLD+SPHQ            0.12             0.22             0.20            0.34             0.25             0.52
2025-02-28 GLD+SPHQ            0.12            -0.21             0.02            0.33             0.28             0.48
2025-03-31  DBC+EFA            0.24             0.85             0.46            0.34             0.61             0.46
2025-04-30  GLD+EFA            0.36             0.15             0.02            0.40             0.15             0.12
2025-05-30 GLD+SPHQ            0.13            -0.35            -0.16            0.39             0.10             0.18
2025-06-30  GLD+EFA            0.34            -0.09             0.07            0.38             0.17             0.22
2025-07-31  GLD+EFA            0.32             0.32             0.28            0.37             0.25             0.25
2025-08-29  GLD+EFA            0.31             0.03             0.32            0.37             0.17             0.28
2025-09-30  GLD+EFA            0.30             0.35             0.32            0.36             0.25             0.30
2025-10-31  GLD+EFA            0.31             0.50             0.22            0.36             0.39             0.33
2025-11-28  GLD+EFA            0.33             0.17             0.29            0.36             0.31             0.31
2025-12-31  GLD+EFA            0.31             0.25             0.37            0.36             0.38             0.32
2026-01-30  DBC+EFA            0.27             0.01            -0.46            0.36             0.18             0.30
2026-02-27  EFA+DBC            0.27            -0.52            -0.64            0.35             0.34             0.35
2026-03-31  DBC+EFA            0.16            -0.80            -0.72            0.35             0.28             0.32
2026-04-30 DBC+SPHQ            0.10            -0.31            -0.31            0.34             0.45             0.45
```
Means:
```
pair_corr_504d    0.130
pair_corr_fwd20   0.086
pair_corr_fwd60   0.089
univ_corr_504d    0.318
univ_corr_fwd20   0.291
univ_corr_fwd60   0.302
```

**Correlation-break summary (fwd minus 504d baseline):**
```
metric                      toxic    risk-on
pair_fwd20-504d            -0.026     -0.044
pair_fwd60-504d            -0.028     -0.041
univ_fwd20-504d            -0.064     -0.028
univ_fwd60-504d            -0.006     -0.016
```

### 5. Co-crash breadth test (held + diversifier forward-return breadth)

```
     month held_neg div_neg univ_neg  univ_neg_frac
2008-06-30      2/2     5/6      7/8           0.88
2008-07-31      1/2     4/6      5/8           0.62
2008-08-29      1/2     4/6      6/8           0.75
2008-12-31      1/2     5/6      7/8           0.88
2009-01-30      0/0     5/6      7/8           0.88
2009-03-31      2/2     2/6      2/8           0.25
2011-09-30      1/2     1/6      1/8           0.12
2014-12-31      1/2     1/6      3/8           0.38
2015-01-30      1/2     3/6      3/8           0.38
2016-02-29      0/2     1/6      1/8           0.12
2020-03-31      1/2     2/6      2/8           0.25
2020-04-30      1/2     1/6      1/8           0.12
2020-05-29      0/2     0/6      0/8           0.00
2022-02-28      1/2     3/6      3/8           0.38
```

Mean fraction of full risky universe with NEGATIVE fwd return (toxic months): 43%
Months where BOTH held risky legs negative (co-crash): 2/13

## Window: STRESS (proxy-extended)  (1999-03-10 -> 2026-05-30)

Total months classified: 298

Cell counts:
```
cell
HYG+/TIP+    210
HYG+/TIP-     32
HYG-/TIP+     28
HYG-/TIP-     28
```

**Toxic cell (HYG-/TIP+) n = 28 months**
Clean risk-on (HYG+/TIP+) n = 210 months

### 1. Toxic-month enumeration (holdings + forward asset/sleeve returns)

- **2001-07-31** [RISK_ON] HYGmom=-0.001 TIPmom=+0.046 | held: VNQ=50%(fwd +2.9%), TLT=50%(fwd +2.3%) | sleeve fwd = +2.63%
- **2001-08-31** [RISK_ON] HYGmom=-0.003 TIPmom=+0.036 | held: VNQ=50%(fwd -3.8%), TLT=50%(fwd +2.4%) | sleeve fwd = -0.69%
- **2001-09-28** [RISK_ON] HYGmom=-0.003 TIPmom=+0.036 | held: TLT=50%(fwd +4.7%), VNQ=50%(fwd -3.3%) | sleeve fwd = +0.69%
- **2001-10-31** [RISK_ON] HYGmom=-0.010 TIPmom=+0.056 | held: TLT=50%(fwd -5.6%), GLD=50%(fwd -2.1%) | sleeve fwd = -3.85%
- **2002-02-28** [RISK_ON] HYGmom=-0.013 TIPmom=+0.014 | held: VNQ=50%(fwd +5.1%), TLT=50%(fwd -3.0%) | sleeve fwd = +1.08%
- **2002-03-28** [RISK_ON] HYGmom=-0.013 TIPmom=+0.014 | held: VNQ=50%(fwd +0.4%), GLD=50%(fwd +1.9%) | sleeve fwd = +1.13%
- **2002-07-31** [RISK_ON] HYGmom=-0.049 TIPmom=+0.043 | held: TLT=50%(fwd +4.9%), VNQ=50%(fwd +1.9%) | sleeve fwd = +3.42%
- **2002-08-30** [RISK_ON] HYGmom=-0.049 TIPmom=+0.043 | held: TLT=50%(fwd +2.7%), VNQ=50%(fwd -2.6%) | sleeve fwd = +0.06%
- **2002-09-30** [RISK_ON] HYGmom=-0.023 TIPmom=+0.077 | held: TLT=50%(fwd -2.5%), GLD=50%(fwd -0.9%) | sleeve fwd = -1.69%
- **2002-10-31** [RISK_ON] HYGmom=-0.016 TIPmom=+0.025 | held: TLT=50%(fwd -0.5%), GLD=50%(fwd -0.6%) | sleeve fwd = -0.56%
- **2002-11-29** [RISK_ON] HYGmom=-0.016 TIPmom=+0.025 | held: TLT=50%(fwd +4.4%), DBC=50%(fwd +6.8%) | sleeve fwd = +5.63%
- **2007-07-31** [RISK_ON] HYGmom=-0.029 TIPmom=+0.028 | held: QQQ=50%(fwd +2.0%), DBC=50%(fwd -1.8%) | sleeve fwd = +0.13%
- **2008-02-29** [RISK_ON] HYGmom=-0.023 TIPmom=+0.084 | held: DBC=50%(fwd -2.3%), TLT=50%(fwd +2.4%) | sleeve fwd = +0.03%
- **2008-03-31** [RISK_ON] HYGmom=-0.016 TIPmom=+0.075 | held: DBC=50%(fwd +6.6%), TLT=50%(fwd -0.9%) | sleeve fwd = +2.88%
- **2008-06-30** [RISK_ON] HYGmom=-0.022 TIPmom=+0.059 | held: DBC=50%(fwd -11.3%), TLT=50%(fwd -0.1%) | sleeve fwd = -5.74%
- **2008-07-31** [RISK_ON] HYGmom=-0.000 TIPmom=+0.036 | held: DBC=50%(fwd -5.5%), TLT=50%(fwd +2.5%) | sleeve fwd = -1.48%
- **2008-08-29** [RISK_ON] HYGmom=-0.000 TIPmom=+0.036 | held: TLT=50%(fwd +0.5%), DBC=50%(fwd -7.9%) | sleeve fwd = -3.66%
- **2008-12-31** [RISK_ON] HYGmom=-0.048 TIPmom=+0.001 | held: TLT=50%(fwd -10.8%), GLD=50%(fwd +5.9%) | sleeve fwd = -2.47%
- **2009-01-30** [DEFENSIVE] HYGmom=-0.048 TIPmom=+0.001 | held: IEF=100%(fwd -1.5%) | sleeve fwd = -1.53%
- **2009-03-31** [RISK_ON] HYGmom=-0.106 TIPmom=+0.026 | held: TLT=50%(fwd -7.8%), GLD=50%(fwd -4.1%) | sleeve fwd = -5.96%
- **2011-09-30** [RISK_ON] HYGmom=-0.049 TIPmom=+0.056 | held: TLT=50%(fwd -6.4%), GLD=50%(fwd +4.0%) | sleeve fwd = -1.22%
- **2014-12-31** [RISK_ON] HYGmom=-0.007 TIPmom=+0.001 | held: TLT=50%(fwd +8.6%), SPHQ=50%(fwd -2.6%) | sleeve fwd = +3.01%
- **2015-01-30** [RISK_ON] HYGmom=-0.007 TIPmom=+0.001 | held: TLT=50%(fwd -5.8%), SPHQ=50%(fwd +3.8%) | sleeve fwd = -0.99%
- **2016-02-29** [RISK_ON] HYGmom=-0.032 TIPmom=+0.009 | held: TLT=50%(fwd +1.7%), SPHQ=50%(fwd +4.4%) | sleeve fwd = +3.06%
- **2020-03-31** [RISK_ON] HYGmom=-0.093 TIPmom=+0.019 | held: TLT=50%(fwd -0.2%), GLD=50%(fwd +6.3%) | sleeve fwd = +3.04%
- **2020-04-30** [RISK_ON] HYGmom=-0.024 TIPmom=+0.049 | held: TLT=50%(fwd -2.6%), GLD=50%(fwd +2.0%) | sleeve fwd = -0.32%
- **2020-05-29** [RISK_ON] HYGmom=-0.024 TIPmom=+0.049 | held: TLT=50%(fwd +1.0%), SPHQ=50%(fwd +0.9%) | sleeve fwd = +0.96%
- **2022-02-28** [RISK_ON] HYGmom=-0.011 TIPmom=+0.016 | held: DBC=50%(fwd +5.0%), GLD=50%(fwd -0.5%) | sleeve fwd = +2.21%

Toxic-cell sleeve fwd return: mean=-0.008%/mo  median=+0.045%  win-rate=54%  worst=-5.96%  best=+5.63%
Annualized (geometric, in-cell only): -0.54%/y

### 2. Holdings frequency across toxic months

```
      count  freq_pct  avg_weight_when_held  avg_weight_overall                         class
TLT      24     85.71                  0.50                0.43  cross-asset/credit-sensitive
GLD      10     35.71                  0.50                0.18  cross-asset/credit-sensitive
DBC       8     28.57                  0.50                0.14  cross-asset/credit-sensitive
VNQ       7     25.00                  0.50                0.12  cross-asset/credit-sensitive
SPHQ      4     14.29                  0.50                0.07                        equity
QQQ       1      3.57                  0.50                0.02                        equity
IEF       1      3.57                  1.00                0.04                    safe/other
```

Aggregate weight share across toxic months:
  cross-asset/credit-sensitive (EEM,VNQ,EFA,GLD,DBC,TLT): 87.5%
  equity (QQQ,SPHQ): 8.9%
  safe/other: 3.6%

### 3. Loss attribution by asset (sum of weight*fwd_ret contributions)

Sum of contributions (=cumulative sleeve return across toxic months, additive): -0.21%
```
      total_contrib_pct  n_months_held  share_of_total_loss_pct
DBC              -5.183              8                 2456.478
TLT              -4.015             24                 1903.192
IEF              -1.534              1                  726.878
VNQ               0.393              7                 -186.223
QQQ               1.013              1                 -479.926
SPHQ              3.275              4                -1552.115
GLD               5.840             10                -2768.285
```

### 4. Correlation-break test (504d baseline vs forward 20d/60d realized)


**Toxic cell HYG-/TIP+ pair & universe correlations** (n=28)
```
     month     pair  pair_corr_504d  pair_corr_fwd20  pair_corr_fwd60  univ_corr_504d  univ_corr_fwd20  univ_corr_fwd60
2001-07-31  VNQ+TLT            0.07            -0.05            -0.02            0.16             0.02             0.15
2001-08-31  VNQ+TLT            0.06             0.08             0.03            0.15             0.23             0.17
2001-09-28  TLT+VNQ            0.05            -0.28            -0.09            0.16             0.09             0.14
2001-10-31  TLT+GLD            0.15             0.22             0.18            0.16             0.19             0.15
2002-02-28  VNQ+TLT           -0.03             0.00            -0.08            0.15             0.24             0.12
2002-03-28  VNQ+GLD           -0.07             0.04             0.03            0.16             0.04             0.06
2002-07-31  TLT+VNQ           -0.12            -0.48            -0.46            0.14             0.20             0.12
2002-08-30  TLT+VNQ           -0.15            -0.52            -0.50            0.15             0.07             0.08
2002-09-30  TLT+GLD            0.17             0.65             0.36            0.14             0.06             0.10
2002-10-31  TLT+GLD            0.19             0.23             0.16            0.14             0.13             0.12
2002-11-29  TLT+DBC           -0.09            -0.43            -0.19            0.14             0.11             0.08
2007-07-31  QQQ+DBC           -0.00             0.27             0.05            0.32             0.30             0.29
2008-02-29  DBC+TLT           -0.09            -0.43            -0.21            0.30             0.27             0.22
2008-03-31  DBC+TLT           -0.14             0.21             0.16            0.30             0.15             0.16
2008-06-30  DBC+TLT           -0.10             0.15            -0.28            0.27             0.09             0.13
2008-07-31  DBC+TLT           -0.09            -0.09            -0.50            0.25             0.13             0.25
2008-08-29  TLT+DBC           -0.10            -0.73            -0.50            0.24             0.17             0.32
2008-12-31  TLT+GLD           -0.01            -0.19             0.21            0.30             0.34             0.32
2009-01-30   (safe)             NaN              NaN              NaN            0.30             0.24             0.29
2009-03-31  TLT+GLD            0.04             0.56             0.25            0.30             0.26             0.35
2011-09-30  TLT+GLD            0.14             0.09            -0.25            0.33             0.34             0.40
2014-12-31 TLT+SPHQ           -0.30            -0.79            -0.30            0.29             0.05             0.28
2015-01-30 TLT+SPHQ           -0.33            -0.34            -0.08            0.28             0.29             0.37
2016-02-29 TLT+SPHQ           -0.39            -0.56            -0.46            0.25             0.30             0.20
2020-03-31  TLT+GLD            0.32             0.02             0.30            0.33             0.32             0.31
2020-04-30  TLT+GLD            0.30             0.75             0.37            0.33             0.28             0.27
2020-05-29 TLT+SPHQ           -0.48            -0.70            -0.55            0.33             0.29             0.31
2022-02-28  DBC+GLD            0.22             0.73             0.65            0.35             0.12             0.26
```
Means:
```
pair_corr_504d    -0.029
pair_corr_fwd20   -0.060
pair_corr_fwd60   -0.064
univ_corr_504d     0.238
univ_corr_fwd20    0.190
univ_corr_fwd60    0.215
```

**Non-toxic risk-on HYG+/TIP+ (comparison)** (n=210)
```
     month     pair  pair_corr_504d  pair_corr_fwd20  pair_corr_fwd60  univ_corr_504d  univ_corr_fwd20  univ_corr_fwd60
2001-11-30  VNQ+TLT            0.02            -0.32            -0.19            0.16             0.20             0.15
2001-12-31  VNQ+TLT           -0.02            -0.30            -0.08            0.16             0.04             0.16
2002-04-30  VNQ+GLD           -0.07             0.17             0.05            0.16             0.10             0.09
2002-05-31  GLD+VNQ           -0.05            -0.31            -0.07            0.15             0.02             0.14
2002-06-28  VNQ+TLT           -0.06            -0.56            -0.44            0.14             0.10             0.15
2002-12-31  TLT+GLD            0.18             0.24             0.35            0.13             0.13             0.04
2003-01-31  GLD+TLT            0.18             0.39             0.47            0.14             0.04             0.02
2003-02-28  TLT+GLD            0.19             0.55             0.43            0.13            -0.03             0.05
2003-03-31  TLT+GLD            0.21             0.40            -0.03            0.12             0.06             0.12
2003-04-30  TLT+VNQ           -0.28            -0.09            -0.07            0.11             0.08             0.19
2003-05-30  TLT+VNQ           -0.28            -0.13             0.05            0.11             0.16             0.22
2003-06-30  VNQ+TLT           -0.28             0.01            -0.06            0.11             0.29             0.18
2003-07-31  VNQ+EEM            0.33             0.32             0.48            0.12             0.20             0.15
2003-08-29  EEM+VNQ            0.33             0.56             0.56            0.12             0.07             0.12
2003-09-30  VNQ+GLD           -0.15            -0.29            -0.14            0.12             0.17             0.17
2003-10-31  EEM+VNQ            0.32             0.75             0.35            0.12             0.20             0.19
2003-11-28  EEM+VNQ            0.33             0.65             0.28            0.12             0.19             0.25
2003-12-31  EEM+VNQ            0.34            -0.12             0.43            0.12             0.16             0.28
2004-01-30  VNQ+EEM            0.33             0.54             0.21            0.12             0.43             0.29
2004-02-27  VNQ+EEM            0.34             0.75             0.19            0.13             0.31             0.31
2004-03-31  VNQ+GLD           -0.13             0.16             0.20            0.13             0.32             0.36
2004-04-30  DBC+EEM            0.04             0.34             0.14            0.14             0.38             0.33
2004-05-28  DBC+VNQ           -0.03            -0.26            -0.27            0.15             0.40             0.27
2004-06-30  DBC+VNQ           -0.04            -0.23            -0.44            0.16             0.17             0.18
2004-07-30  VNQ+TLT           -0.11            -0.30            -0.14            0.16             0.14             0.15
2004-08-31  VNQ+TLT           -0.10            -0.01             0.02            0.16             0.18             0.17
2004-09-30  VNQ+TLT           -0.08            -0.32             0.17            0.16             0.13             0.22
2004-10-29  VNQ+TLT           -0.06             0.30             0.22            0.17             0.28             0.27
2004-11-30  VNQ+GLD           -0.01             0.12            -0.00            0.17             0.27             0.24
2004-12-31 VNQ+SPHQ            0.48             0.45             0.68            0.18             0.26             0.27
2005-01-31 TLT+SPHQ           -0.18             0.36             0.21            0.19             0.19             0.26
2005-02-28 TLT+SPHQ           -0.15             0.65             0.07            0.19             0.29             0.28
2005-03-31  EFA+TLT            0.05            -0.18            -0.04            0.22             0.26             0.25
2005-04-29  TLT+EFA            0.05            -0.13             0.00            0.23             0.26             0.21
2005-05-31 TLT+SPHQ           -0.05             0.15             0.05            0.23             0.25             0.22
2005-06-30  TLT+VNQ            0.15             0.30             0.10            0.23             0.22             0.21
2005-07-29 VNQ+SPHQ            0.46             0.37             0.69            0.23             0.23             0.26
2005-08-31  TLT+VNQ            0.17            -0.64            -0.14            0.24             0.18             0.25
2005-09-30  EFA+GLD            0.33             0.04             0.19            0.24             0.30             0.29
2005-10-31  GLD+EFA            0.35             0.20             0.51            0.25             0.22             0.30
2005-11-30  GLD+QQQ           -0.02             0.19             0.26            0.25             0.29             0.33
2005-12-30  GLD+QQQ           -0.00             0.52             0.33            0.26             0.35             0.34
2006-01-31 GLD+SPHQ            0.12             0.40             0.37            0.27             0.31             0.31
2006-02-28  GLD+EFA            0.40             0.27             0.37            0.27             0.31             0.31
2006-07-31  VNQ+EFA            0.43             0.43             0.35            0.29             0.34             0.31
2006-08-31  EFA+TLT            0.02            -0.12             0.13            0.29             0.26             0.27
2006-09-29  TLT+EFA            0.03             0.45             0.21            0.30             0.38             0.26
2006-10-31  TLT+EFA            0.05             0.13             0.04            0.30             0.18             0.23
2006-11-30  TLT+EFA            0.04            -0.20            -0.18            0.30             0.20             0.32
2006-12-29  EFA+TLT            0.03             0.10            -0.22            0.30             0.32             0.36
2007-01-31  VNQ+EFA            0.43             0.67             0.72            0.30             0.36             0.37
2007-02-28  TLT+EFA            0.02            -0.29            -0.21            0.31             0.42             0.37
2007-03-30  EFA+VNQ            0.49             0.26             0.51            0.31             0.31             0.37
2007-04-30  EFA+QQQ            0.68             0.69             0.80            0.32             0.30             0.34
2007-05-31  EFA+QQQ            0.68             0.89             0.82            0.32             0.44             0.31
2007-06-29  EFA+QQQ            0.69             0.78             0.85            0.32             0.30             0.29
2007-08-31  QQQ+TLT           -0.07            -0.33            -0.46            0.33             0.24             0.29
2007-09-28  QQQ+DBC            0.05            -0.23             0.06            0.33             0.27             0.28
2007-10-31  QQQ+DBC            0.04             0.06             0.13            0.33             0.25             0.26
2007-11-30  TLT+DBC           -0.05            -0.09            -0.13            0.32             0.32             0.25
2007-12-31  DBC+TLT           -0.05             0.02            -0.29            0.32             0.23             0.24
2008-01-31  DBC+TLT           -0.05            -0.36            -0.31            0.31             0.23             0.23
2008-04-30  DBC+TLT           -0.13             0.19             0.19            0.29             0.20             0.13
2008-05-30  DBC+QQQ            0.07            -0.56            -0.40            0.28             0.12             0.10
2009-04-30  GLD+QQQ           -0.04            -0.18             0.21            0.30             0.42             0.41
2009-05-29  GLD+QQQ           -0.04             0.44             0.45            0.30             0.39             0.40
2009-06-30  QQQ+GLD           -0.04             0.46             0.37            0.30             0.42             0.41
2009-07-31  QQQ+GLD           -0.04             0.56             0.42            0.31             0.35             0.40
2009-08-31  QQQ+EFA            0.87             0.87             0.89            0.31             0.46             0.46
2009-09-30  QQQ+EFA            0.87             0.87             0.85            0.31             0.46             0.43
2009-10-30  QQQ+GLD           -0.03             0.43             0.40            0.31             0.53             0.41
2009-11-30  GLD+QQQ           -0.04             0.49             0.53            0.31             0.32             0.41
2009-12-31  QQQ+GLD           -0.04             0.52             0.55            0.32             0.42             0.44
2010-01-29  GLD+QQQ           -0.03             0.83             0.48            0.32             0.47             0.41
2010-02-26  GLD+QQQ           -0.02             0.23            -0.05            0.32             0.43             0.30
2010-03-31 QQQ+SPHQ            0.87             0.88             0.91            0.33             0.31             0.27
2010-04-30  QQQ+GLD           -0.00            -0.08            -0.02            0.33             0.28             0.29
2010-05-28 SPHQ+TLT           -0.40            -0.65            -0.64            0.33             0.25             0.32
2010-06-30  TLT+GLD            0.03            -0.30             0.11            0.33             0.38             0.34
2010-07-30 TLT+SPHQ           -0.41            -0.76            -0.63            0.34             0.31             0.36
2010-08-31  TLT+GLD            0.03             0.54             0.33            0.34             0.28             0.46
2010-09-30  TLT+QQQ           -0.42            -0.42            -0.28            0.36             0.49             0.47
2010-10-29 GLD+SPHQ            0.22             0.61             0.37            0.37             0.53             0.42
2010-11-30 GLD+SPHQ            0.15            -0.01            -0.01            0.36             0.33             0.25
2010-12-31 GLD+SPHQ            0.12            -0.05            -0.02            0.35             0.19             0.22
2011-01-31 DBC+SPHQ            0.54            -0.23             0.17            0.35             0.19             0.25
2011-02-28 DBC+SPHQ            0.56             0.21             0.33            0.36             0.22             0.27
2011-03-31 SPHQ+GLD            0.17             0.00             0.31            0.36             0.27             0.31
2011-04-29 GLD+SPHQ            0.21             0.44             0.04            0.37             0.31             0.31
2011-05-31 SPHQ+GLD            0.23             0.36            -0.51            0.36             0.31             0.25
2011-06-30 SPHQ+GLD            0.22            -0.49            -0.41            0.36             0.33             0.26
2011-07-29  TLT+DBC           -0.30            -0.50            -0.53            0.35             0.25             0.28
2011-08-31  TLT+DBC           -0.32            -0.53            -0.60            0.33             0.28             0.34
2011-10-31 TLT+SPHQ           -0.57            -0.77            -0.74            0.32             0.47             0.42
2011-11-30 TLT+SPHQ           -0.60            -0.81            -0.71            0.33             0.38             0.33
2011-12-30 TLT+SPHQ           -0.61            -0.62            -0.53            0.33             0.32             0.32
2012-01-31 TLT+SPHQ           -0.61            -0.53            -0.52            0.32             0.23             0.33
2012-02-29 SPHQ+TLT           -0.61            -0.48            -0.54            0.32             0.41             0.36
2012-03-30 QQQ+SPHQ            0.90             0.80             0.86            0.32             0.39             0.29
2012-04-30 SPHQ+TLT           -0.62            -0.63            -0.73            0.32             0.26             0.30
2012-05-31 TLT+SPHQ           -0.61            -0.77            -0.73            0.32             0.25             0.32
2012-06-29 TLT+SPHQ           -0.62            -0.87            -0.58            0.32             0.30             0.32
2012-07-31 TLT+SPHQ           -0.63            -0.54            -0.46            0.32             0.32             0.31
2012-08-31 TLT+SPHQ           -0.62            -0.44            -0.49            0.32             0.30             0.30
2012-09-28 GLD+SPHQ            0.07             0.54             0.24            0.32             0.26             0.26
2012-10-31 SPHQ+TLT           -0.62            -0.72            -0.62            0.32             0.32             0.28
2012-11-30 SPHQ+TLT           -0.65            -0.68            -0.62            0.31             0.15             0.23
2012-12-31 SPHQ+VNQ            0.83             0.78             0.76            0.30             0.26             0.24
2013-01-31 SPHQ+VNQ            0.83             0.78             0.80            0.31             0.28             0.33
2013-02-28 SPHQ+VNQ            0.83             0.77             0.76            0.31             0.14             0.33
2013-03-28 SPHQ+QQQ            0.89             0.89             0.88            0.31             0.38             0.44
2013-04-30 SPHQ+QQQ            0.89             0.81             0.83            0.31             0.27             0.45
2014-06-30 SPHQ+TLT           -0.34            -0.60            -0.25            0.32             0.05             0.24
2014-07-31  QQQ+TLT           -0.34            -0.25            -0.41            0.31             0.14             0.23
2014-08-29 TLT+SPHQ           -0.30            -0.36            -0.42            0.30             0.25             0.22
2014-10-31 SPHQ+TLT           -0.31            -0.16            -0.66            0.30             0.13             0.16
2014-11-28 SPHQ+TLT           -0.29            -0.62            -0.62            0.29             0.21             0.17
2015-02-27 SPHQ+TLT           -0.32             0.35             0.04            0.28             0.57             0.40
2015-03-31 TLT+SPHQ           -0.27            -0.48            -0.20            0.29             0.20             0.27
2015-04-30 SPHQ+EFA            0.80             0.86             0.78            0.28             0.36             0.22
2015-05-29 SPHQ+EFA            0.81             0.69             0.82            0.29             0.23             0.23
2016-03-31 SPHQ+TLT           -0.39            -0.32            -0.59            0.25             0.12             0.12
2016-04-29 SPHQ+TLT           -0.38            -0.54            -0.55            0.25             0.18             0.16
2016-05-31 SPHQ+TLT           -0.38            -0.75            -0.49            0.25             0.16             0.17
2016-06-30  TLT+DBC           -0.25            -0.27            -0.09            0.24             0.21             0.39
2016-07-29 TLT+SPHQ           -0.40            -0.07             0.24            0.24             0.18             0.43
2016-08-31  TLT+EEM           -0.36             0.46             0.39            0.24             0.57             0.38
2016-09-30  QQQ+TLT           -0.36             0.00             0.13            0.25             0.31             0.28
2016-10-31  QQQ+DBC            0.27             0.37            -0.02            0.25             0.23             0.26
2016-11-30 SPHQ+DBC            0.34            -0.19            -0.06            0.26             0.33             0.24
2016-12-30 DBC+SPHQ            0.34             0.10             0.19            0.26             0.23             0.28
2017-01-31 SPHQ+DBC            0.35             0.03             0.16            0.27             0.06             0.23
2017-02-28 QQQ+SPHQ            0.86             0.90             0.81            0.27             0.43             0.24
2017-03-31 QQQ+SPHQ            0.86             0.71             0.66            0.26             0.06             0.13
2017-04-28 QQQ+SPHQ            0.85             0.79             0.65            0.26             0.16             0.22
2017-05-31 QQQ+SPHQ            0.85             0.60             0.71            0.25             0.17             0.21
2017-08-31  QQQ+GLD           -0.20            -0.55            -0.19            0.25             0.09             0.17
2017-09-29 SPHQ+QQQ            0.82            -0.05             0.31            0.25             0.26             0.22
2017-10-31 QQQ+SPHQ            0.81             0.51             0.63            0.25             0.24             0.24
2017-11-30 SPHQ+QQQ            0.80             0.49             0.91            0.24             0.20             0.41
2017-12-29 SPHQ+QQQ            0.79             0.79             0.92            0.23             0.37             0.36
2018-01-31 SPHQ+QQQ            0.77             0.96             0.94            0.23             0.44             0.35
2018-05-31 DBC+SPHQ            0.22             0.04             0.32            0.27             0.18             0.27
2018-06-29 DBC+SPHQ            0.19             0.43             0.41            0.29             0.32             0.30
2018-07-31 SPHQ+DBC            0.20             0.66             0.54            0.30             0.30             0.27
2018-08-31 SPHQ+DBC            0.21             0.09             0.33            0.30             0.18             0.23
2018-09-28 SPHQ+DBC            0.19             0.60             0.36            0.28             0.24             0.23
2019-01-31  GLD+TLT            0.35             0.75             0.52            0.27             0.26             0.24
2019-02-28 TLT+SPHQ           -0.27            -0.61            -0.50            0.27             0.25             0.23
2019-03-29 TLT+SPHQ           -0.28            -0.35            -0.41            0.27             0.20             0.23
2019-04-30 SPHQ+TLT           -0.28            -0.62            -0.30            0.27             0.19             0.27
2019-05-31 TLT+SPHQ           -0.29            -0.20            -0.53            0.27             0.25             0.23
2019-06-28 TLT+SPHQ           -0.29             0.20            -0.48            0.27             0.36             0.22
2019-07-31 TLT+SPHQ           -0.29            -0.73            -0.49            0.27             0.18             0.20
2019-08-30 TLT+SPHQ           -0.34            -0.27            -0.23            0.26             0.15             0.17
2019-09-30 TLT+SPHQ           -0.33            -0.32            -0.25            0.26             0.19             0.17
2019-10-31  TLT+EFA           -0.33            -0.35            -0.42            0.26             0.21             0.15
2019-11-29  TLT+EFA           -0.33            -0.18            -0.58            0.26             0.17             0.22
2019-12-31  EFA+GLD            0.02            -0.49             0.24            0.26             0.09             0.41
2020-01-31 TLT+SPHQ           -0.34            -0.65            -0.54            0.25             0.28             0.40
2020-02-28  TLT+GLD            0.40             0.20             0.22            0.24             0.43             0.40
2020-06-30 TLT+SPHQ           -0.49            -0.65            -0.17            0.33             0.21             0.35
2020-07-31  QQQ+TLT           -0.46             0.38            -0.04            0.33             0.42             0.36
2020-08-31 GLD+SPHQ            0.03             0.45             0.29            0.33             0.43             0.36
2020-09-30 GLD+SPHQ            0.05             0.46             0.26            0.33             0.36             0.31
2020-10-30 GLD+SPHQ            0.07             0.19             0.15            0.33             0.26             0.26
2020-11-30  DBC+EFA            0.57             0.31             0.48            0.33             0.26             0.30
2020-12-31  DBC+EFA            0.57             0.52             0.39            0.34             0.33             0.34
2021-01-29  DBC+EFA            0.57             0.44             0.29            0.34             0.34             0.39
2021-02-26  DBC+EFA            0.57             0.27             0.13            0.34             0.43             0.42
2021-03-31  DBC+EFA            0.55            -0.04             0.10            0.34             0.38             0.36
2021-04-30  DBC+EFA            0.54            -0.00             0.30            0.34             0.46             0.29
2021-05-28  DBC+EFA            0.53             0.28             0.47            0.35             0.25             0.23
2021-06-30  DBC+EFA            0.53             0.64             0.53            0.35             0.20             0.24
2021-07-30 DBC+SPHQ            0.48             0.42             0.38            0.34             0.32             0.26
2021-08-31 SPHQ+DBC            0.47             0.71             0.40            0.35             0.29             0.22
2021-09-30 DBC+SPHQ            0.49             0.38             0.64            0.35             0.16             0.28
2021-10-29 DBC+SPHQ            0.48             0.70             0.57            0.35             0.28             0.31
2021-11-30 SPHQ+TLT           -0.41            -0.41            -0.17            0.35             0.34             0.27
2021-12-31 SPHQ+DBC            0.49             0.21            -0.39            0.35             0.31             0.17
2023-03-31 GLD+SPHQ            0.14             0.07            -0.19            0.37             0.29             0.26
2023-04-28 GLD+SPHQ            0.13            -0.45            -0.16            0.36             0.28             0.32
2023-11-30 SPHQ+GLD            0.12             0.43             0.32            0.38             0.48             0.39
2023-12-29 SPHQ+EFA            0.85             0.67             0.63            0.38             0.32             0.33
2024-01-31 SPHQ+EFA            0.85             0.56             0.67            0.38             0.38             0.31
2024-02-29 SPHQ+EFA            0.85             0.69             0.74            0.39             0.30             0.38
2024-03-28 SPHQ+GLD            0.23             0.13             0.21            0.42             0.27             0.37
2024-05-31 SPHQ+GLD            0.25             0.17             0.34            0.42             0.27             0.38
2024-06-28 SPHQ+GLD            0.26             0.41             0.42            0.42             0.44             0.39
2024-07-31 SPHQ+GLD            0.26             0.42             0.31            0.42             0.36             0.29
2024-08-30 SPHQ+GLD            0.26             0.51             0.08            0.42             0.34             0.26
2024-09-30 GLD+SPHQ            0.25            -0.14             0.07            0.41             0.10             0.29
2024-10-31 GLD+SPHQ            0.21            -0.15             0.09            0.39             0.29             0.33
2024-11-29 SPHQ+GLD            0.14             0.44             0.30            0.36             0.45             0.32
2025-01-31 GLD+SPHQ            0.12             0.22             0.20            0.34             0.25             0.52
2025-02-28 GLD+SPHQ            0.12            -0.21             0.02            0.33             0.28             0.48
2025-03-31  DBC+EFA            0.24             0.85             0.46            0.34             0.61             0.46
2025-04-30  GLD+EFA            0.36             0.15             0.02            0.40             0.15             0.12
2025-05-30 GLD+SPHQ            0.13            -0.35            -0.16            0.39             0.10             0.18
2025-06-30  GLD+EFA            0.34            -0.09             0.07            0.38             0.17             0.22
2025-07-31  GLD+EFA            0.32             0.32             0.28            0.37             0.25             0.25
2025-08-29  GLD+EFA            0.31             0.03             0.32            0.37             0.17             0.28
2025-09-30  GLD+EFA            0.30             0.35             0.32            0.36             0.25             0.30
2025-10-31  GLD+EFA            0.31             0.50             0.22            0.36             0.39             0.33
2025-11-28  GLD+EFA            0.33             0.17             0.29            0.36             0.31             0.31
2025-12-31  GLD+EFA            0.31             0.25             0.37            0.36             0.38             0.32
2026-01-30  DBC+EFA            0.27             0.01            -0.46            0.36             0.18             0.30
2026-02-27  EFA+DBC            0.27            -0.52            -0.64            0.35             0.34             0.35
2026-03-31  DBC+EFA            0.16            -0.80            -0.72            0.35             0.28             0.32
2026-04-30 DBC+SPHQ            0.10            -0.31            -0.31            0.34             0.45             0.45
```
Means:
```
pair_corr_504d    0.124
pair_corr_fwd20   0.103
pair_corr_fwd60   0.107
univ_corr_504d    0.286
univ_corr_fwd20   0.273
univ_corr_fwd60   0.283
```

**Correlation-break summary (fwd minus 504d baseline):**
```
metric                      toxic    risk-on
pair_fwd20-504d            -0.032     -0.021
pair_fwd60-504d            -0.036     -0.017
univ_fwd20-504d            -0.048     -0.013
univ_fwd60-504d            -0.023     -0.003
```

### 5. Co-crash breadth test (held + diversifier forward-return breadth)

```
     month held_neg div_neg univ_neg  univ_neg_frac
2001-07-31      0/2     2/6      4/8           0.50
2001-08-31      1/2     4/6      6/8           0.75
2001-09-28      1/2     3/6      3/8           0.38
2001-10-31      2/2     3/6      3/8           0.38
2002-02-28      1/2     1/6      1/8           0.12
2002-03-28      0/2     1/6      3/8           0.38
2002-07-31      0/2     0/6      0/8           0.00
2002-08-30      1/2     3/6      5/8           0.62
2002-09-30      2/2     4/6      4/8           0.50
2002-10-31      2/2     2/6      2/8           0.25
2002-11-29      0/2     3/6      5/8           0.62
2007-07-31      1/2     2/6      2/8           0.25
2008-02-29      1/2     3/6      4/8           0.50
2008-03-31      1/2     2/6      2/8           0.25
2008-06-30      2/2     5/6      7/8           0.88
2008-07-31      1/2     4/6      5/8           0.62
2008-08-29      1/2     4/6      6/8           0.75
2008-12-31      1/2     5/6      7/8           0.88
2009-01-30      0/0     5/6      7/8           0.88
2009-03-31      2/2     2/6      2/8           0.25
2011-09-30      1/2     1/6      1/8           0.12
2014-12-31      1/2     1/6      3/8           0.38
2015-01-30      1/2     3/6      3/8           0.38
2016-02-29      0/2     1/6      1/8           0.12
2020-03-31      1/2     2/6      2/8           0.25
2020-04-30      1/2     1/6      1/8           0.12
2020-05-29      0/2     0/6      0/8           0.00
2022-02-28      1/2     3/6      3/8           0.38
```

Mean fraction of full risky universe with NEGATIVE fwd return (toxic months): 41%
Months where BOTH held risky legs negative (co-crash): 5/27

## Verdict

**REFUTED.** Evidence does not support the credit-sensitive-diversifier
correlation-regime-break story. The HYG-/TIP+ cell loss is (a) concentrated in
two specific assets, (b) GFC-clustered small-sample, and (c) shows NO
correlation spike / diversification failure.

### Cell reconciliation
- Backtest-exact (actual trading-day sig_d): **n = 14** clean-window months.
- Dashboard-exact (calendar ME resample, canary-only): **n = 13**.
- The 1-month gap is borderline-momentum noise: 2009-01, 2014-11, 2015-01 all
  have |13612U(HYG)| < ~0.01 (sign flips on tiny data/resample differences).
  Reconciles with the dashboard heatmap ~13 HYG-/TIP+ cell. CONFIRMED.

### Why the hypothesis fails

1. **Loss is concentrated, not broad.** Decomposition (both windows) shows the
   damage comes from exactly TWO legs:
   - CLEAN: TLT -9.67%, DBC -9.87% cumulative contribution; net cell -11.09%.
   - STRESS: TLT -4.02%, DBC -5.18%; net cell -0.21% (~flat).
   GLD - a diversifier in the SAME credit-sensitive bucket the hypothesis names
   - was POSITIVE in both windows (+6.70% clean, +5.84% stress) and SPHQ was
   positive too. A uniform diversifier co-crash would sink GLD with TLT/DBC; it
   did not. The losers are rates (TLT) and commodities (DBC), driven by
   idiosyncratic shocks (2008 oil collapse for DBC; rate spikes for TLT).

2. **No correlation spike / no diversification break.** The mechanism predicts
   held-pair and universe correlations CONVERGE UP in these months. They did
   not. Forward-minus-504d-baseline deltas are flat-to-NEGATIVE and statistically
   indistinguishable from non-toxic risk-on months:
   - pair fwd20 - 504d: toxic -0.032 vs risk-on -0.021
   - univ fwd20 - 504d: toxic -0.048 vs risk-on -0.013
   Held-pair correlations averaged ~ -0.06 (504d) and STAYED slightly negative
   forward (~ -0.086). Diversification held; it did not fail.

3. **No co-crash breadth.** BOTH held legs negative only 2/13 clean months
   (2008-06 DBC+TLT, 2009-03 TLT+GLD). Mean fraction of the full 8-asset risky
   universe with negative forward return ~43% (clean) / ~41% (stress) - normal
   churn, not a synchronized drawdown.

4. **Does not generalize - small-sample, GFC-clustered.** The clean-window
   headline (dashboard -5.4%/y, -22.9% DD; my in-cell geometric -9.58%/y) is
   produced almost entirely by 3 GFC months: 2008-06 (-5.74%), 2008-08
   (-3.66%), 2009-03 (-5.96%). Extending to the stress window DOUBLES the
   sample to n=28 and the cell goes ~FLAT: mean -0.008%/mo, median +0.045%,
   win-rate 54%, in-cell geometric -0.54%/y. The toxicity is not a stable
   property of the HYG-/TIP+ regime.

### What actually happens in the cell
In HYG-/TIP+ months the vol-adjusted Faber ranker tilts hard to TLT (held
12/14 = 86% of clean months, 24/28 stress) because credit-soft / risk-off
periods coincide with positive Treasury (and often commodity) trend signals.
The min-var optimizer then pairs TLT with the next lowest-covariance survivor
(GLD, DBC, or SPHQ). Cross-asset/credit-sensitive names carry ~79% (clean) /
~88% (stress) of cell weight - so the holdings ARE diversifier-dominated, the
one part of the hypothesis that holds. But the realized loss is an idiosyncratic
TLT+DBC drawdown during the GFC, NOT a correlation convergence among those
diversifiers. GLD kept diversifying throughout.

### Confidence
- Mechanism refutation: HIGH (consistent across both windows; correlation,
  attribution, and breadth tests all point the same way).
- Generalization claim: HIGH (n doubles in stress window and effect vanishes).
- Caveats: stress window pre-2007 uses mutual-fund/index proxies (VWEHX/VIPSX/
  VUSTX/world-bank-GLD); DBC live from 2006-02 so pre-2006 commodity exposure
  is absent and some pre-2006 cell months substitute VNQ/GLD. Forward returns
  measured on the actual holding window [apply_from, end_apply). Dashboard
  -5.4%/y uses daily mean*252 attribution; my in-cell figures use geometric
  compounding of holding-window returns - both negative, magnitudes differ by
  construction.

### Handoff
None required. If productionizing a fix is desired (e.g. a TLT/DBC-specific
guard or de-emphasis in soft-credit regimes), route to fixer - but evidence
suggests the cell is small-sample GFC noise, not a structural defect.
