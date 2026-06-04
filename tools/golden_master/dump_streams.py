# /tmp/gm/dump_streams.py (does NOT modify repo; pure read)
import argparse
import json
import os
import numpy as np
import pandas as pd
import cpm_live
import bull_spy_live
import rpv_live
import ndx_sleeve_live
import value_sleeve_live
import build_dashboard as bd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end")
    ap.add_argument("--out")
    a = ap.parse_args()
    end = pd.Timestamp(a.end)
    out = a.out
    os.makedirs(out, exist_ok=True)
    
    start = pd.Timestamp("2008-05-30")
    panel = cpm_live.load_panel(start=start, end=end)        # frozen, no live
    ndx_panel = ndx_sleeve_live.load_ndx_panel()

    # A: close-to-close engine
    cpm_cc, _  = cpm_live.run_cpm_backtest(panel, start, end)
    bull_cc    = bull_spy_live.run_bull_spy_backtest(panel, start, end)
    ndx_cc, _  = ndx_sleeve_live.run_ndx_backtest(panel, ndx_panel, start, end)
    rpv_cc     = rpv_live.run_rpv_backtest(panel, start, end)

    # A/B/D: mooex/blend engine (the authoritative one)
    art = bd.build_artifacts(panel, ndx_panel, start, end, include_records=True)

    streams = {
        "cpm_cc": cpm_cc,
        "bull_cc": bull_cc,
        "ndx_cc": ndx_cc,
        "rpv_cc": rpv_cc,
        "cpm_mooex": art.cpm,
        "rpv_mooex": art.rpv_raw,
        "ndx_mooex": art.ndx_raw,
        "val_mooex": art.val_raw,
        "blend": art.blend,
        "blend_uncapped": art.blend_uncapped,
    }
    for name, s in streams.items():
        if s is not None and not s.empty:
            s.to_frame("ret").to_parquet(f"{out}/{name}.parquet")
            # also a deterministic text dump for easy diffing
            s.to_csv(f"{out}/{name}.csv", float_format="%.12g")

    for name in ("cpm_records", "rpv_records", "ndx_records", "val_records"):
        recs = getattr(art, name, [])
        with open(f"{out}/{name}.json", "w") as f:
            json.dump(recs, f, sort_keys=True, default=str, indent=0)

    with open(f"{out}/mooex_coverage.json", "w") as f:
        json.dump(art.mooex_coverage, f, sort_keys=True)

if __name__ == '__main__':
    main()
