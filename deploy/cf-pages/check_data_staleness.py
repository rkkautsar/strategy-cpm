#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

DAILY_THRESH_DAYS = 7
MONTHLY_THRESH_DAYS = 75
BAA_THRESH_DAYS = 45
EARNINGS_THRESH_DAYS = 210

DAILY_SERIES = ["DGS10", "DGS3MO", "DBAA", "DAAA", "AAA", "SP500"]
MONTHLY_SERIES = ["CPIAUCSL", "SAHMREALTIME"]


def _last_obs_date(csv_path: Path) -> pd.Timestamp | None:
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    if df.empty:
        return None
    date_col = df.columns[0]
    dts = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dts.empty:
        return None
    return dts.max().normalize()


def build_warnings(signal_month_end: pd.Timestamp) -> list[str]:
    warnings: list[str] = []

    def check(label: str, path: Path, max_age_days: int) -> None:
        latest = _last_obs_date(path)
        if latest is None:
            warnings.append(f"- {label}: missing or unreadable ({path.name})")
            return
        age = (signal_month_end - latest).days
        if age > max_age_days:
            warnings.append(
                f"- {label}: latest {latest.date()} is {age}d before signal month-end {signal_month_end.date()} (>{max_age_days}d)"
            )

    for sid in DAILY_SERIES:
        check(sid, DATA_DIR / f"fred_{sid}.csv", DAILY_THRESH_DAYS)

    for sid in MONTHLY_SERIES:
        check(sid, DATA_DIR / f"fred_{sid}.csv", MONTHLY_THRESH_DAYS)

    check("BAA", DATA_DIR / "fred_BAA.csv", BAA_THRESH_DAYS)
    check("sp500_earnings", DATA_DIR / "sp500_earnings.csv", EARNINGS_THRESH_DAYS)

    return warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data_staleness_warnings.txt")
    args = parser.parse_args()

    today = pd.Timestamp.today().normalize()
    signal_month_end = today.replace(day=1) - pd.Timedelta(days=1)

    warnings = build_warnings(signal_month_end)

    out_path = ROOT / args.out
    if warnings:
        out_path.write_text("\n".join(warnings) + "\n", encoding="utf-8")
    else:
        out_path.write_text("", encoding="utf-8")

    if warnings:
        print("DATA STALENESS WARNINGS:")
        for line in warnings:
            print(line)
    else:
        print("No staleness warnings.")


if __name__ == "__main__":
    main()
