# CPM Turn-of-Month: Temporal Decay + Already-Discounted Check

Read-only analyst investigation. Reuses production signal/weight functions from
`cpm_live.py` and the `research/cpm_execution_cliff.py` timing harness, both
unchanged. Only the measurement window over the day-since-rebalance attribution
is varied. No production or memo files were edited; nothing was committed.

- Harness: `research/cpm_tom_decay.py` (imports `cpm_cc_returns`, `sharpe_of`
  from `research/cpm_execution_cliff.py`)
- Artifacts: `research/cpm_tom_decay_findings.json`
- Run: `.venv/bin/python research/cpm_tom_decay.py`
- Convention: close-to-close (cc), `exec_lag=0`, 10 bps/side, EOM config
  `(eom, 0)` -- identical to the prior execution-cliff battery so numbers are
  apples-to-apples. Anchor: full clean (2008-05-30..2026-05-22) EOM Sharpe
  **1.206** cc (1.191 t1_moo). The realistic T+1 MOO convention captures the same
  day-1 premium; cc is used here only to match the prior harness.
- Method: returns and day-since-rebalance labels are computed ONCE over the full
  clean window (same rebalance basket sequence as the headline backtest), then
  sliced by date subperiod. Day-1 after an EOM rebalance is the first trading
  day of the month -- the turn-of-month (TOM) window.

## Question

Prior work attributed ~0.10-0.20 of the ~1.19-1.21 headline Sharpe to a
turn-of-month effect (full-window: day-1 ~14.9 bp vs ~4.9 bp rest-of-month;
removing day-1 drops Sharpe ~0.10). Two open questions the critique raised:

1. Is that 0.10-0.20 empirically grounded over TIME (tested by subperiod, does
   it decay), or only a structural inference from the EOM knife-edge?
2. The 2017-26 half shows Sharpe ~1.38. If TOM has already decayed by then, the
   strong recent Sharpe is NOT TOM-driven and the microstructure concern is
   partly already discounted in the clean number. Quantify.

## 1. Temporal decay by subperiod (EMPIRICAL)

Day-since-rebalance attribution measured separately on each subperiod. `SR drop`
= full-slice Sharpe minus Sharpe with day-1 rows removed = the TOM contribution
to that subperiod's Sharpe.

| Subperiod | day-1 bp | rest bp | day1/rest | day-1 SR | day-1 share P&L | full SR | excl-day1 SR | SR drop (TOM) |
|-----------|----------|---------|-----------|----------|-----------------|---------|--------------|---------------|
| 2008-12   | 22.7     | 3.9     | 5.80x     | 3.56     | 22.5%           | 0.929   | 0.767        | **0.162**     |
| 2013-17   | 9.4      | 5.0     | 1.89x     | 2.49     | 8.7%            | 1.497   | 1.443        | **0.054**     |
| 2018-22   | 19.0     | 4.1     | 4.61x     | 4.63     | 18.7%           | 1.118   | 0.953        | **0.165**     |
| 2023-26   | 6.2      | 7.1     | 0.87x     | 1.52     | 4.2%            | 1.489   | 1.489        | **0.001**     |

Rolling 5y day-1 (bp / standalone Sharpe), decay curve:

| 5y window | day-1 bp | day-1 SR |   | 5y window | day-1 bp | day-1 SR |
|-----------|----------|----------|---|-----------|----------|----------|
| 2008-2012 | 22.7     | 3.56     |   | 2016-2020 | 12.4     | 3.58     |
| 2009-2013 | 22.7     | 3.59     |   | 2017-2021 | 21.7     | 5.28     |
| 2010-2014 | 11.9     | 2.36     |   | 2018-2022 | 19.0     | 4.63     |
| 2011-2015 | 4.9      | 1.13     |   | 2019-2023 | 24.7     | 6.44     |
| 2012-2016 | 4.1      | 1.07     |   | 2020-2024 | 25.7     | 6.28     |
| 2013-2017 | 9.4      | 2.49     |   | 2021-2025 | 17.7     | 4.40     |
| 2014-2018 | 1.0      | 0.28     |   | 2022-2026 | 7.2      | 1.91     |
| 2015-2019 | 6.0      | 1.90     |   |           |          |          |

Reading: the TOM premium is **NOT monotonically decaying**. It is
**regime-dependent and noisy**: strong in crisis/recovery high-vol regimes
(2008-09 GFC recovery ~22 bp; 2018-22 incl. COVID 19 bp; rolling peak 2019-2024
~25 bp), and weak/absent in calm bull regimes (2011-2016 trough ~4-5 bp; 2014-2018
~1 bp; **2023-26 6.2 bp**). A clean crowding/arbitrage story predicts monotonic
decay -- the data shows a strong REVIVAL in 2017-2024, contradicting simple
monotonic erosion.

Critically, the **most recent subperiod (2023-26)** is the key forward signal:
day-1 (6.2 bp) is BELOW rest-of-month (7.1 bp). The day1/rest multiple is 0.87x
(below 1.0), day-1's P&L share is only 4.2%, and removing day-1 changes the
Sharpe by **0.001** (1.489 -> 1.489). TOM as an EXCESS over the rest-of-month is
effectively GONE in the current regime.

## 2. Already-discounted check: 2008-16 vs 2017-26 halves

| Half     | full SR | day-1 bp | rest bp | day-1 share P&L | excl-day1 SR | SR from TOM |
|----------|---------|----------|---------|-----------------|--------------|-------------|
| 2008-16  | 1.028   | 14.8     | 4.1     | 15.2%           | 0.926        | **0.102**   |
| 2017-26  | 1.376   | 14.9     | 5.6     | 11.9%           | 1.268        | **0.108**   |

Reading: at the HALF-window level, TOM still contributes ~0.10 Sharpe in BOTH
halves -- the day-1 bp is essentially identical across halves (14.8 vs 14.9). So
naively the recent half is "not yet discounted." BUT decompose WHERE the recent
half's outperformance comes from:

- day-1 bp barely moved: 14.8 -> 14.9 (TOM did NOT grow).
- rest-of-month improved materially: 4.1 -> 5.6 bp; rest-of-month standalone
  Sharpe 0.93 -> 1.27.

So the jump from 1.03 to 1.38 half-Sharpe is driven by the **rest-of-month
(momentum core), NOT by TOM**. The recent strong Sharpe is momentum-core-driven.

The 0.108 TOM in the 2017-26 half is itself carried almost entirely by the
2017-2022 COVID-era spike (subperiod 2018-22 SR drop 0.165), NOT by the live
tail: the 2023-26 subperiod contributes ~0.001. Aggregating 2017-26 into one
window masks that the live (2023+) TOM is near zero.

## 3. Empirical vs structural label (for the memo)

Precise, correctly-labeled statement:

- **EMPIRICAL (measured):** The full-window day-1 attribution -- ~14.9 bp day-1
  vs ~4.9 bp rest-of-month, ~3x, removing day-1 drops Sharpe ~0.10 -- is a
  direct empirical measurement, not an inference. The per-subperiod decay table
  and the half-window split above are ALSO direct empirical measurements.
- **EMPIRICAL finding on time-variation:** The TOM premium is regime-dependent
  and noisy, NOT monotonically decaying. It is strong in crisis/recovery vol
  regimes and weak/absent in calm bull regimes; in the current regime (2023-26)
  it is effectively absent (day-1 6.2 bp < rest 7.1 bp; SR drop 0.001).
- **INFERENCE (not proven):** "Crowding/arbitrage is steadily eroding TOM going
  forward" is an inference, and the data does NOT support a simple monotonic
  crowding story (TOM revived strongly 2017-2024). What the data DOES support is
  that TOM is currently dormant and that the recent clean Sharpe is not relying
  on it.

## Verdict

1. **Decaying or stable?** Neither -- the TOM premium is **regime-dependent /
   cyclical**, not a clean monotonic decay. It is currently **dormant**: in
   2023-26 day-1 (6.2 bp) sits below rest-of-month (7.1 bp), so there is no live
   excess TOM premium in the current regime. But it has revived in past high-vol
   regimes (2008-09, 2018-22), so it is not permanently arbitraged away either.

2. **Already discounted in the recent number?** **Largely yes for the live
   tail.** The recent strength (half-Sharpe 1.38) is driven by the rest-of-month
   momentum core (rest bp 4.1 -> 5.6), not by TOM (day-1 bp flat ~14.9). In the
   most recent subperiod (2023-26) TOM adds ~0.001 Sharpe. The ~0.108 TOM still
   booked in the full 2017-26 half is a 2017-2022 (COVID-era) artifact, not a
   live edge. So the strong recent clean Sharpe is NOT TOM-inflated -- the
   microstructure concern is mostly already discounted in the current-regime
   number.

3. **Forward execution-cliff haircut implication -- refine SMALLER, regime-aware:**
   - The full-window 0.10-0.20 TOM number is empirical but PERIOD-AVERAGED and
     dominated by crisis-era spikes (2008-09, 2018-22). Using it as a flat
     forward haircut OVERSTATES the current drag.
   - In the current regime there is no live TOM premium to lose, so the
     execution-cliff haircut on the FORWARD Sharpe should be **smaller** than the
     headline 0.10-0.20 -- closer to ~0.00-0.05 for the TOM component
     specifically, conditional on a calm/low-vol regime persisting.
   - Caveat (do not zero it out): TOM revives in crisis/high-vol regimes, where
     execution slippage and month-end crowding also worsen. So budget a small
     STATE-CONTINGENT TOM haircut (~0 in calm regimes, up to ~0.15 in
     high-vol/crisis regimes) rather than a flat number.
   - The execution-cliff sensitivity itself (EOM 1.21 -> EOM+1 1.01, ~0.19) is a
     separate signal-freshness + alignment effect and is NOT removed by the TOM
     finding; that part remains a live execution-discipline requirement.

Net: the headline 0.10-0.20 TOM estimate is real and empirical as a HISTORICAL
period average, but it is regime-cyclical and currently dormant; the recent clean
Sharpe (~1.38) does not depend on it, so the forward execution-cliff haircut
attributable to TOM specifically should be small (state-contingent), not the
full historical 0.10-0.20.

## Caveats and confidence

- Confidence HIGH that TOM is regime-dependent (not monotonic decay) and that
  the 2023-26 subperiod shows no live day-1 excess: the day-1 < rest-of-month
  inversion and the 0.001 SR drop are unambiguous, computed from the same engine
  as the headline.
- Confidence MEDIUM on the exact forward haircut magnitude: subperiod day-1
  counts are small (~55-113 day-1 observations), so individual subperiod day-1 bp
  has wide error bars; the regime pattern is robust but point estimates are
  noisy.
- Confidence MEDIUM on "already discounted": the half-window TOM is still ~0.10,
  and the "live tail near zero" conclusion rests on the most recent ~3.4y
  subperiod (53 day-1 obs). If a high-vol regime returns, TOM likely revives.
- Single strategy, one universe, cc convention, 10 bps/side, no month-end
  slippage modeling. Throwaway research artifacts only; no production behavior
  changed; nothing committed.
