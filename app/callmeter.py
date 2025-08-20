# app/callmeter.py
from __future__ import annotations
import csv
import os
from pathlib import Path
from datetime import datetime, timezone

METER_PATH = Path(os.getenv("GT_METER_PATH", "/data/gt_meter.csv"))


def _nowiso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_header():
    METER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not METER_PATH.exists():
        with METER_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "ts_utc", "run_id", "phase", "topic_mid", "timeframe",
                "geo", "attempt", "status", "error"
            ])


def log_call(run_id: str, phase: str, topic_mid: str, timeframe: str, geo: str,
             attempt: int, status: str, error: str = ""):
    ensure_header()
    with METER_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([_nowiso(), run_id, phase, topic_mid,
                   timeframe, geo, attempt, status, error])


class CallBudget:
    """Compteur/seuil par run."""

    def __init__(self, max_calls: int = 5):
        self.max_calls = max_calls
        self.count = 0

    def hit(self):
        self.count += 1
        if self.count > self.max_calls:
            raise RuntimeError(
                f"Call budget exceeded: {self.count}/{self.max_calls}")
