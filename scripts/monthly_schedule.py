from __future__ import annotations

import argparse
import calendar
from datetime import date, timedelta

import exchange_calendars as xc


def schedule(session: date) -> tuple[bool, date | None]:
    last_day = calendar.monthrange(session.year, session.month)[1]
    start = session.replace(day=1)
    end = session.replace(day=last_day)
    market = xc.get_calendar("XNYS", start=start.isoformat(), end=(end + timedelta(days=14)).isoformat())
    sessions = market.sessions_in_range(start.isoformat(), end.isoformat())
    if sessions.empty or sessions[-1].date() != session:
        return False, None
    return True, market.next_session(session.isoformat()).date()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("date", type=date.fromisoformat)
    args = parser.parse_args()
    due, execution = schedule(args.date)
    print(f"due={'true' if due else 'false'}")
    if execution:
        print(f"execution_date={execution.isoformat()}")
