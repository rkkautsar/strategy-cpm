# Monthly trend signals for QQQ — research + empirical comparison

## Executive summary

- **Practitioner default**: Faber 10-month SMA (Faber 2007) — simple, low turnover, well-adopted.
- **Academic strongest**: 12-1 absolute momentum (Antonacci dual momentum; Moskowitz TSMOM) — robust across centuries and asset classes.
- **Empirical winner for MAX-TOP2 sleeve**: **12-1 momentum > 0** — best blend Sharpe on extended 28y window AND best dot-com robustness (-16.1% blend DD vs -22.5% for current Faber 10mo).
- Keller 13612W is **not appropriate** for single-asset timing (designed for breadth/safe rotation; empirical Sh 0.76 worst).
- No single signal catches COVID flash crash (Feb 19 → Mar 23, 2020) — all show the full -28.6% drop on QQQ buy-hold timing tests. Macro VIX gate handles this in MAX-TOP2.

## Signals reviewed

### 1. Faber 10-month SMA (Faber 2007)
- **Source**: M. Faber, "A Quantitative Approach to Tactical Asset Allocation," SSRN/JoWM (2006/2007). [PDF](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf)
- **Rule**: monthly close > 10-month SMA → in equity; else cash.
- **Original results**: S&P 500 sample, CAGR 10.18% vs B&H 9.32%, materially lower MaxDD.
- **Faber notes**: stability across 3-12 month variants.
- **Adoption**: very high in TAA practitioner space (Cambria, AllocateSmartly, many bloggers).
- **Pros**: simple, low turnover, parameter stability.
- **Cons**: whipsaws in choppy markets; lags re-entry on fast rallies.

### 2. Antonacci 12-1 absolute momentum
- **Source**: Antonacci, "Risk Premia Harvesting Through Dual Momentum" SSRN (2012). [PDF](https://papers.ssrn.com/abstract=2042750). Also Moskowitz/Ooi/Pedersen, "Time Series Momentum," JFE (2012). [PDF](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)
- **Rule**: 12-month total return (excluding most recent month) > safe-asset return → in equity; else safe.
- **Reported results**: Dual Momentum 1971-2016, CAGR ~16.7%, Sharpe ~0.87, MaxDD ~-17.8% (Antonacci).
- **Adoption**: strong academic + practitioner backing.
- **Pros**: well-tested, lower DD, simple.
- **Cons**: lags re-entries (misses early rally); whipsaws possible.

### 3. Keller 13612W (HAA/VAA)
- **Source**: Keller & Keuning, "Breadth Momentum and Vigilant Asset Allocation," SSRN (2017). [PDF](https://papers.ssrn.com/abstract=3002624)
- **Rule**: weighted score `(12*r1 + 4*r3 + 2*r6 + r12) / 19` > 0 → in asset.
- **Designed for**: breadth-protected rotation across multi-asset universe with canary gating, NOT single-asset timing.
- **Empirical on QQQ alone**: WORST single-asset signal tested (Sh 0.76 vs 0.86-0.94 for others).
- **Verdict**: don't use for per-asset filtering. Keep for safe-pool rotation in FCP sleeve.

### 4. Time-series momentum (3, 6, 12 month returns)
- **Source**: Jegadeesh & Titman 1993; Moskowitz/Ooi/Pedersen 2012.
- **Rule**: total return over N months > 0 (or > safe asset).
- **Empirical**: 6mo and 12mo are most cited. Shorter lookbacks (3-6mo) sometimes better for tech (Ahmed & Alhadab 2020 sector study).

### 5. Monthly EMA crossovers
- **Sources**: Practitioner (TradingView, QuantSignals, blog posts). No canonical academic paper.
- **Note**: EMA(2) monthly ≈ EMA(50) daily; EMA(10) monthly ≈ EMA(200) daily. The "daily 50/200 golden cross" maps to EMA(2)/EMA(10) monthly.
- **Empirical on QQQ**: EMA 3/12 monthly performed well (Sh 0.93); EMA 2/10 monthly (proper monthly equivalent of daily 50/200) was mediocre (Sh 0.81).

## Empirical comparison

### Single-asset QQQ ↔ SHV cash timing (LIVE 18y, post-cost 10bps/side)

| Signal | Sharpe | CAGR | MaxDD | %on |
|---|---:|---:|---:|---:|
| QQQ buy-hold (reference) | **0.89** | **18.66%** | -35.12% | 100% |
| **Faber 6mo SMA** | **0.94** | 15.16% | -28.56% | 78% |
| EMA 3/12 monthly | 0.93 | 16.98% | -28.72% | 89% |
| 12-1 momentum > 0 | 0.92 | 16.51% | -28.72% | 88% |
| 3mo total return > 0 | 0.92 | 14.53% | -28.56% | 76% |
| SMA 3/10 monthly | 0.89 | 15.34% | -28.56% | 83% |
| SMA 2/10 monthly | 0.89 | 14.65% | -28.56% | 80% |
| Faber 10mo SMA | 0.86 | 13.85% | -28.56% | 80% |
| EMA 2/10 monthly (≈daily 50/200) | 0.81 | 13.98% | -33.00% | 86% |
| Faber 12mo SMA | 0.81 | 12.96% | -28.56% | 80% |
| Keller 13612W | 0.76 | 11.99% | -33.04% | 78% |

**Key findings:**
- QQQ buy-hold is hard to beat on Sharpe (Sh 0.89) on the live window; tech ran too strong.
- All signals show -28.6% COVID DD — no monthly signal catches a 5-week flash crash. Macro VIX gate handles this in MAX-TOP2.
- Slow filters (EMA 2/10 monthly, Faber 12mo) underperform on tech.
- Faber 6mo wins the live window; 12-1 momentum is a close second.

### MAX-TOP2 context (top-2 from {QQQ,SMH,SCHG,XLK,IWM} + macro gate, 70/30 blend with FCP)

| Per-asset filter | LIVE 18y blend Sh / CAGR / DD | EXT 28y blend Sh / CAGR / DD |
|---|---:|---:|
| Faber 10mo (current) | 1.29 / 13.6% / -10.3% | 0.98 / 10.6% / **-22.5%** |
| Faber 6mo dist > 0 | **1.32** / 13.8% / -10.3% | 1.00 / 10.6% / -21.4% |
| **12-1 momentum > 0** | 1.30 / 13.7% / -12.4% | **1.02 / 10.9% / -16.1%** |
| EMA 3/12 monthly | 1.31 / 14.0% / -12.6% | 0.99 / 10.7% / -21.6% |
| 12-1 AND Faber 10mo (hybrid) | 1.28 / 13.2% / -10.5% | 0.99 / 10.4% / -16.1% |

## Recommendation for MAX-TOP2

**Switch per-asset filter from Faber 10mo distance > 0 to 12-1 absolute momentum > 0.**

**Rationale:**
- 12-1 momentum has the strongest academic backing (Antonacci, Moskowitz/Ooi/Pedersen).
- Wins blend Sharpe on extended 28y (1.02 vs 0.98) — robustness across regime types.
- Massive dot-com DD improvement: blend -16.1% vs -22.5% for current Faber 10mo (-6.4pp better).
- Standalone CAGR +1.2pp on extended (11.0% vs 9.8%).

**Costs (live 18y):**
- -0.02 blend Sharpe (1.32 → 1.30, within noise)
- +2.1pp blend DD (-10.3% → -12.4%, but live window missed dot-com so this DD is a window artifact)

**Why not Faber 6mo (best on live):**
- Live window's clean DD is partly because it didn't get tested by dot-com.
- Faber 6mo standalone DD on extended is -56.7% vs 12-1 mom -41.2%; 15pp DD difference matters for a sleeve that's supposed to be the bull-capture overlay.

**Why not the literature-recommended hybrid (12-1 AND Faber 10mo):**
- Empirically didn't win. Adds restriction (more time in cash) without improving DD or Sharpe materially.

## Implementation notes

Pseudocode for new per-asset filter:

```python
def momentum_12m(s: pd.Series, sig_d: pd.Timestamp) -> float:
    """12-month absolute total return (Antonacci/Moskowitz)."""
    sd = s.loc[:sig_d].dropna()
    if len(sd) < 13:
        return float("nan")
    return float(sd.iloc[-1] / sd.iloc[-13] - 1)

def passes_filter(s: pd.Series, sig_d: pd.Timestamp) -> bool:
    m = momentum_12m(s, sig_d)
    return pd.notna(m) and m > 0
```

Ranking metric for top-K selection: keep current 10-month Faber distance (it's a stable cross-sectional ranker even if not used as the eligibility filter). Or could use 12-1 momentum value itself.

## Sources

- Faber (2007). "A Quantitative Approach to Tactical Asset Allocation." [SSRN PDF](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf)
- Antonacci (2012). "Risk Premia Harvesting Through Dual Momentum." [SSRN](https://papers.ssrn.com/abstract=2042750)
- Antonacci, "Absolute Momentum." [SSRN](https://papers.ssrn.com/abstract=2244633)
- Moskowitz, Ooi, Pedersen (2012). "Time Series Momentum," JFE. [PDF](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)
- Jegadeesh, Titman (1993). "Returns to Buying Winners and Selling Losers," JoF.
- Keller & Keuning (2017). "Breadth Momentum and Vigilant Asset Allocation," [SSRN](https://papers.ssrn.com/abstract=3002624)
- TrendXplorer VAA: https://indexswingtrader.blogspot.com/2017/07/breadth-momentum-and-vigilant-asset.html
- RogueQuant QQQ trend test: https://roguequant.substack.com/p/the-too-simple-to-work-qqq-strategy
- TalkMarkets QQQ momentum: https://talkmarkets.com/content/investing-ideas--strategies/how-to-benefit-from-trend-and-momentum-in-qqq?post=241744
- CXO Advisory: https://www.cxoadvisory.com/technical-trading/10-month-sma-timing-signals-over-the-short-run/
- Ahmed & Alhadab (2020). "Momentum ... Does technology-sector matter?" Quarterly Review of Economics and Finance.
