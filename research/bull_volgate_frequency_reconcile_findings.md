# BULL vol-gate cross-era divergence: data-frequency artifact, or genuine regime?

Role: analyst (read-only re production; writes only research/; no production/memo edits; no commit).
EXPLORATION ONLY -- validity check informing a design decision about whether the BULL
slow vol gate (rv_60d < rv_252d) grind-protection is a real, repeatable mechanism.

## Question

The vol gate gives contradictory verdicts across eras:
- MODERN (`research/bull_volgate_episode_decomp_findings.md`): EARNS in slow grinds 2018-Q4
  and 2022 (+7.96pp and +9.81pp DD vs trend-only HAA).
- 1970s (`research/stagflation_1970s_bull_stack*`, `research/vol_gate_timing_hysteresis*`):
  WHIPSAWED / was BLIND to the 1977-82 grind, ~coin-flip, cost CAGR.

User hypothesis: divergence may be a DATA-FREQUENCY ARTIFACT (1970s coarser data smooths
vol -> gate under-fires/mis-times). Investigate rigorously.

## Method

1. Confirm the rv_60d / rv_252d computation frequency in each era's harness (exact line refs).
2. If frequencies differ -> run modern-on-monthly decisive test.
3. If frequencies match -> inspect actual rv_60 vs rv_252 STATE through each grind.

rv recomputed independently here from the same source files both harnesses load.

## 1. FREQUENCY CONFIRMATION -- both eras use REAL DAILY returns

### MODERN (production + harnesses): DAILY

- `bull_qqq_live.py:103-114` `_vol_gate_ok(daily_spy, sig_d)`:
  ```
  108: sub = daily_spy.loc[:sig_d].pct_change().dropna()
  111: rv_60  = float(sub.tail(60).std()  * np.sqrt(252))
  112: rv_252 = float(sub.tail(252).std() * np.sqrt(252))
  113: vol_ok = rv_60 < rv_252
  ```
  DAILY simple returns, trailing 60 / 252 trading days, annualized sqrt(252).
- Harness `research/exec_lag_moo_validation_2026_05_30.py:55-66` `gate_rv(fast,slow=252)`:
  identical -- `sub = daily_spy.loc[:sig_d].pct_change().dropna()`, `tail(fast/slow).std()*sqrt(252)`.
  `GATE_RV60 = gate_rv(60)` is the production gate under test.
- `research/bull_tiponly_recompute.py:44-47` imports the same harness + `bull_qqq_live`;
  it monkeypatches in `_vol_gate_ok` (the daily gate). No resampling of the vol input.
- daily_spy source = `data/proxy_adjusted_close_daily.csv` column `SPY` (true daily close).
- NOTE: the monthly `resample("ME")` at `bull_qqq_live.py:148` is for the TREND/canary panel
  ONLY (13612U momentum), NOT the vol gate. Vol gate input stays daily.

### 1970s (stagflation harnesses): also DAILY

- `research/stagflation_1970s_trend_vol.py:69-72` `load_daily_sp()` reads
  `research/data_1970s/gspc_daily.csv` -- Yahoo Finance ^GSPC **true daily close**,
  4770 obs, 1967-01..1985-12 (verified: 4771 lines incl header; ~252*19). NOT monthly,
  NOT interpolated.
- `research/stagflation_1970s_trend_vol.py:76-96` `vol_gate_monthly(daily_close)`:
  ```
  79: r = np.log(daily_close / daily_close.shift(1)).dropna()
  95: rv_fast = float(fast.std(ddof=0) * np.sqrt(252))   # trailing 60 DAILY log rets
  96: rv_slow = float(slow.std(ddof=0) * np.sqrt(252))   # trailing 252 DAILY log rets
  ```
  DAILY log returns, trailing 60 / 252 trading days, annualized sqrt(252), evaluated at
  each month-end (month-end is the SAMPLING cadence of the signal, not the rv frequency).
- `research/stagflation_1970s_bull_stack.py:63` and
  `research/vol_gate_timing_hysteresis.py:88` both `from stagflation_1970s_trend_vol import
  load_daily_sp, vol_gate_monthly` -- they consume this exact daily-derived gate.
- Self-documented in `stagflation_1970s_trend_vol.py:29-40,185,195`: "S&P 500 DAILY close:
  Yahoo Finance ^GSPC daily ... Used ONLY for the VOL gate (rv_60d / rv_252d)."

Only difference: simple returns (modern) vs log returns (1970s). Immaterial for daily-window
realized vol -- both are trailing daily-return std * sqrt(252). Same frequency, same windows.

VERDICT on frequency: **frequencies MATCH (both real daily).** The 1970s harness does NOT
use monthly or monthly-interpolated data for the vol gate -- it uses genuine ^GSPC daily.
The data-frequency-artifact hypothesis is **REFUTED at the source level.** The modern-on-monthly
decisive test is therefore moot and (per scope) was not run.

(For completeness: the 1970s TREND signal does use Shiller monthly-average price, and the
modern TREND/canary uses month-end resample -- but that asymmetry is identical in structure
across eras and is orthogonal to the vol gate. The vol gate input is daily in both.)

## 2. Frequencies MATCH -> inspect rv_60 vs rv_252 STATE through each grind

`vol_on = True` means rv_60 < rv_252 = risk-ON (gate does NOT de-risk).
`vol_on = False` means rv_60 >= rv_252 = vol expansion = de-risk.

### MODERN 2022 (the KEY "earns" episode): VOL-EXPANSION grind

| month | rv60 | rv252 | spread pp | state |
|---|---:|---:|---:|---|
| 2021-11 | 0.127 | 0.122 | +0.5 | de-risk |
| 2021-12 | 0.135 | 0.130 | +0.6 | de-risk |
| 2022-01 | 0.165 | 0.132 | +3.3 | de-risk |
| 2022-02 | 0.192 | 0.139 | +5.3 | de-risk |
| 2022-03 | 0.216 | 0.149 | +6.8 | de-risk |
| 2022-06 | 0.287 | 0.198 | +8.8 | de-risk |
| ... | ... | ... | ... | de-risk (11 of 12 mo 2022) |

rv_60 crossed ABOVE rv_252 at the grind's onset (Nov 2021) and stayed above the whole year.
The gate de-risked AT THE TOP and held -> caught the bear (BULL DD -0.30% vs HAA -10.11%,
+9.81pp). This is a vol-EXPANSION grind.

### MODERN 2018 (Q4 selloff): VOL-EXPANSION at the turn

rv_60 expanded above rv_252 Feb-May (volmageddon), reverted risk-on Jun-Sep, then re-crossed
ABOVE for Oct/Nov/Dec (0.146>0.140, 0.177>0.149, 0.240>0.170) exactly as the Q4 selloff hit
-> de-risked into Q4 -> earned (+7.96pp DD vs HAA).

### 1970s 1977-82 grind: LOW-VOL-PERSISTENT onset + chronic whipsaw

| month | rv60 | rv252 | spread pp | state |
|---|---:|---:|---:|---|
| 1977-01 | 0.097 | 0.106 | -0.9 | risk-ON |
| 1977-02 | 0.081 | 0.101 | -2.0 | risk-ON |
| 1977-03 | 0.076 | 0.098 | -2.2 | risk-ON |
| 1977-05 | 0.095 | 0.097 | -0.2 | risk-ON |
| 1977-08 | 0.081 | 0.094 | -1.4 | risk-ON |
| 1977-10 | 0.083 | 0.089 | -0.6 | risk-ON |
| 1977-11 | 0.103 | 0.091 | +1.2 | de-risk (too late) |

Through the ENTIRE first 10 months of the 1977 slow bleed (1977-01..1977-10), rv_60 stayed
BELOW rv_252 -- the gate never de-risked, rode the grind down. The decline was slow and
LOW-VOL-PERSISTENT: short-term vol did not expand above the trailing year, so the crossover
never triggered until the damage was done. Over the full 1977-82 window: 72 months,
36 risk-on / 36 de-risk (coin-flip, no edge), and 15 state flips = chronic whipsaw in the
1977-78 chop. Matches the prior 58% false-positive / CAGR-cost finding.

## Mechanism (confirmed)

The gate fires on rv_60 >= rv_252 -- short-term vol EXPANDING above the trailing-year baseline.
- It EARNS when a grind arrives WITH a vol expansion (2018-Q4, 2022): the selloff lifts
  short-term realized vol above the year-trailing level, the crossover trips, the gate
  de-risks early/at the top.
- It FAILS when a grind is LOW-VOL-PERSISTENT (1977-82 stagflation bleed): the slow decline
  keeps short-term vol at/below the trailing-year baseline, the crossover never trips, the
  gate stays risk-on and rides it down -- and in the surrounding chop it whipsaws.

This is not a frequency effect; it is the same daily-rv gate responding to two structurally
different grind types.

## VERDICT

(b) **GENUINE REGIME DISTINCTION** -- vol-expansion grind vs low-vol-persistent grind.
The data-frequency-artifact hypothesis (a) is **REFUTED**: both eras compute rv_60d/rv_252d
from REAL DAILY returns (modern `data/proxy_adjusted_close_daily.csv` SPY; 1970s Yahoo ^GSPC
`gspc_daily.csv`, 4770 daily obs -- not monthly, not interpolated), identical 60/252 trailing
windows, identical sqrt(252) annualization. The modern "earns in grinds" result is real at
the 1970s's frequency because the frequency is the SAME.

CONSEQUENCE FOR TRUST: the vol gate's grind-protection is real but CONDITIONAL. It is
repeatable for vol-EXPANSION grinds (the type 2018-Q4 and 2022 were) and structurally
BLIND to low-vol-persistent grinds (the type 1977-82 was). Do NOT generalize the modern
"earns in grinds" finding to "earns in ALL grinds." The mechanism is "de-risk on short-term
vol expansion," which only some bear grinds carry. Confidence: HIGH on frequency parity
(direct source lines + independent recompute); HIGH on the regime mechanism (rv state series
align cleanly with the earns/whipsaw verdicts in all four windows).

## Caveats

- 1970s vol gate uses price-only ^GSPC (no dividends) -- irrelevant for realized vol.
- 1970s equity sleeve return is Shiller monthly TR; the trend signal uses Shiller
  monthly-average price (documented in-harness). These do not touch the vol gate.
- Modern vs 1970s rv use simple vs log daily returns respectively -- immaterial for
  daily-window realized-vol comparison.
- This study isolates the rv STATE/mechanism; it does not re-run full P&L (already in the
  cited decomp/stagflation findings).
