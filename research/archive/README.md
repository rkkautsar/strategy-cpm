# Archived experiments

This directory contains 119 one-off exploration scripts and their logs from
the multi-session research trail that produced the current production spec.

Files here are NOT referenced by the production code or main README. They
are preserved for audit / historical reproducibility only.

## Contents (by theme)

- `aggressive_*` -- early bull-tilt overlay experiments (superseded by
  current BULL-QQQ sleeve)
- `canary_*` -- canary rule design exploration (3-asset HYG+LQD+TIP for BULL,
  3-asset HYG+TIP+GLD for FCP, "any-positive" rule selected)
- `hold_buffer_*` -- hold-buffer threshold experiments (2.5z selected; see
  `../hold_buffer_threshold_diagnosis.log` for the kept summary)
- `universe_*` -- universe pruning sweeps (11-asset universe selected)
- `fcp_aaa_*` -- decomposition vs Resolve AAA fund (head-to-head kept in
  `../fcp_vs_resolve_live.log`)
- `lowcorr_*`, `optimum3_test`, `pair_holdbuffer` -- pair-selection
  experiments (min-variance pair selected)
- `stitch_*` -- proxy-stitching scripts for pre-ETF history (output CSVs
  live in `../../data/`)
- `signal_lag_sweep`, `tsmom_variants`, `mf_mr_*` -- signal design experiments
- `dd_*` -- drawdown-based circuit breaker experiments (rejected)
- `inception.py`, `2009_2010_analysis.py`, `frozen_eom.py` -- historical
  spot-checks
- `chain_stitch_*`, `dbmf_long_history_test`, `build_sg_cta_dbmf` -- data
  source building for one experiment

## Why archived, not deleted

- Future audits may want to verify what was tested and rejected
- Provides paper trail for "we did consider X, here's why it didn't win"
- DSR multiple-testing haircut assumes ~1000 trials; these are part of
  that selection history

## What's NOT here

Production-relevant artifacts kept at `research/` root:
- Oracle review series (`oracle_v2/v3/v4/v6/v7/v8_*.log`)
- Session summaries (`session_2026_05*.md`, `strategy_summary.md`,
  `run_manifest_2026.md`)
- Cited validation logs (DSR, override removal, canary asymmetry,
  hold-buffer threshold, peer comparison, regime attribution, etc.)
- Narrative docs (`canary_state_rotation_notes.md`,
  `monthly_qqq_signals.md`, etc.)
