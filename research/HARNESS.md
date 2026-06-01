# CPM research harness

Use `research/cpm_harness.py` first. It is canonical wrapper over existing engine + production weight function.

## What this harness locks

- Engine: `exec_lag_moo_validation_2026_05_30._segment_returns_conv`
- Execution convention: `mooex` T+1 MOO exact
  - old basket earns overnight `close[T] -> open[t+1]`
  - new basket earns intraday `open[t+1] -> close[t+1]`
  - compounded on rebalance day
- Trading costs: 10 bps per side
- Windows:
  - clean: `2008-05-30..end`
  - ext: `1999-03-10..end`
- Baseline guard: both-252 (`cpm_live.CORR_LOOKBACK_DAYS == 252`)
- Open-cache source: `exec_lag_moo_validation_2026_05_30.load_open_close()`
  - includes auto-adjust contamination guard (`|close/open - 1|` sanity check)

## API

```python
from research import cpm_harness as H

data = H.load_data()
returns = H.run_strategy(weight_fn, window="clean", data=data)
stats = H.metrics(returns, data=data)
H.verify_anchor(data=data)
```

### `load_data()`
Returns canonical panel + open cache inputs (`panel`, `open_df`, `close_yf`, `intraday`, `overnight`, `cash`) and window bounds.

### `run_strategy(weight_fn, window="clean")`
Runs `weight_fn` through mooex engine, post-cost.

Accepted `weight_fn` forms:
- `(panel, sig_d) -> dict[str, float]`
- `(sig_d) -> dict[str, float]`
- tuple-returning forms where weights are element 0 (for direct `compute_target_weights` usage)

### `metrics(returns)`
Returns:
- `Sharpe`
- `Calmar`
- `Martin`
- `MaxDD`
- `CAGR`
- `vol`

### `verify_anchor()`
One-call gate. Runs production `cpm_live.compute_target_weights` through harness and asserts clean both-252 anchor:

- Sharpe: `1.1658`
- MaxDD: `-12.97%` (`-0.1297`)
- Calmar: `1.0137`

Raises clear `AssertionError` if off tolerance.

## Plugging custom weight functions

You can build HAA-style or CPM variants with production helpers from `cpm_live`:

- `sig_13612U` (unweighted)
- `faber_sma_xs`
- `inv_vol_weights`
- `best_safe`
- `compute_target_weights`

Example: production CPM direct

```python
from cpm_live import compute_target_weights
from research import cpm_harness as H

data = H.load_data()
r = H.run_strategy(compute_target_weights, window="clean", data=data)
print(H.metrics(r, data=data))
```
