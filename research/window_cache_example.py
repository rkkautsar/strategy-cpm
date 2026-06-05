from __future__ import annotations

import argparse
import os

import pandas as pd

from research.window_cache import get_sleeve_window
from research.window_cache_adapters import get_window_adapter


def compute_research_sleeve_window(
    sleeve: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    verify: bool = False,
) -> pd.Series:
    """Research-only helper. Opt-in via WINDOW_CACHE=1."""
    adapter = get_window_adapter(sleeve)
    return get_sleeve_window(
        adapter.sleeve,
        start,
        end,
        segment_compute_fn=adapter.segment_compute_fn,
        max_lookback=adapter.max_lookback,
        version=adapter.version,
        params=adapter.params,
        source_files=adapter.source_files,
        data_identity=adapter.data_identity,
        atol=adapter.atol,
        enable=None,
        verify=verify,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only window cache example")
    parser.add_argument("--sleeve", default="cpm", choices=["cpm", "rpv", "ndx", "val"])
    parser.add_argument("--start", default="2008-05-30")
    parser.add_argument("--end", default="2026-04-30")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)

    print(f"WINDOW_CACHE={os.environ.get('WINDOW_CACHE', '0')} (set 1 to enable compose cache)")
    s = compute_research_sleeve_window(args.sleeve, start, end, verify=args.verify)
    print(f"{args.sleeve} rows={len(s)} min={s.index.min().date() if len(s) else 'n/a'} max={s.index.max().date() if len(s) else 'n/a'}")


if __name__ == "__main__":
    main()
