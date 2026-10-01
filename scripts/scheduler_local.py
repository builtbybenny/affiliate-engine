#!/usr/bin/env python3
"""Local scheduler: runs the daily slot at the right local time.

Alternative to GitHub Actions. Keep a terminal open (or a Windows Task
Scheduler / cron entry) and this posts twice a day forever, free.

  python scripts/scheduler_local.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()
from core import config

CHECK_EVERY = 60  # seconds


def run_step(script: str, *args: str) -> None:
    cmd = [sys.executable, f"scripts/{script}", *args]
    print(f"[{config.now_local():%Y-%m-%d %H:%M}] $ {' '.join(cmd)}")
    subprocess.run(cmd, check=False)


def next_slot(now: datetime) -> tuple[datetime, str]:
    """Next (datetime, format) slot from POST_TIMES for today or tomorrow."""
    today = now.date()
    entries = config.WEEKLY_CALENDAR.get(today.strftime("%a").lower(), [])
    if not entries:
        entries = [("carousel", "product_spotlight")]
    slots: list[tuple[datetime, str]] = []
    for fmt, _ in entries:
        hh, mm = config.POST_TIMES[fmt].split(":")
        slots.append((datetime(today.year, today.month, today.day, int(hh), int(mm), tzinfo=now.tzinfo), fmt))
    slots.sort()
    for dt, fmt in slots:
        if dt > now:
            return dt, fmt
    # tomorrow: first format on tomorrow's calendar
    tmrw = today + timedelta(days=1)
    t_entries = config.WEEKLY_CALENDAR.get(tmrw.strftime("%a").lower(), [("carousel", "product_spotlight")])
    fmt0 = t_entries[0][0]
    hh, mm = config.POST_TIMES[fmt0].split(":")
    return datetime(tmrw.year, tmrw.month, tmrw.day, int(hh), int(mm), tzinfo=now.tzinfo), fmt0


def main() -> None:
    print(f"Local scheduler started (TZ offset {config.TZ_OFFSET}). Ctrl+C to stop.")
    # 'done' keys: (date, format) already handled
    done: set[tuple[str, str]] = set()
    while True:
        now = config.now_local()
        dt, fmt = next_slot(now)
        wait = (dt - now).total_seconds()
        print(f"[{now:%H:%M}] next slot: {fmt} at {dt:%Y-%m-%d %H:%M} (sleeping {int(wait)}s)")
        time.sleep(max(1, min(wait, 3600)))
        now = config.now_local()
        key = (now.date().isoformat(), fmt)
        if now >= dt and key not in done:
            run_step("generate.py", "--today", "--format", fmt)
            run_step("publish.py", "--today", "--format", fmt)
            done.add(key)
            # cap memory of the set
            if len(done) > 200:
                done = set(sorted(done)[-50:])


if __name__ == "__main__":
    main()
