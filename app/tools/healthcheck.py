from __future__ import annotations
import csv
import sys
import os
from pathlib import Path
from datetime import datetime, date

DATA = Path("/data")
TODAY = date.today()


def latest_file(pattern: str) -> Path | None:
    files = sorted(DATA.glob(pattern))
    return files[-1] if files else None


def to_int(x, default=0):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return default


def read_calls_summary(p: Path) -> dict:
    with p.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
        cols = {c.lower() for c in (r.fieldnames or [])}

    metrics = {"total_calls": 0, "ok_2xx": 0, "err_4xx": 0, "err_5xx": 0}

    if {"total_calls", "ok_2xx", "err_4xx", "err_5xx"} <= cols:
        row = rows[0]
        for k in metrics:
            metrics[k] = to_int(row.get(k, 0))
        return metrics

    for row in rows:
        status = str(row.get("status") or row.get("code") or "").strip()
        n = to_int(row.get("count") or row.get("n") or 0)
        if not status:
            continue
        try:
            s = int(status)
        except Exception:
            continue
        metrics["total_calls"] += n
        if 200 <= s <= 299:
            metrics["ok_2xx"] += n
        elif 400 <= s <= 499:
            metrics["err_4xx"] += n
        elif 500 <= s <= 599:
            metrics["err_5xx"] += n
    return metrics


def read_meter_summary(p: Path) -> dict:
    total = 0
    with p.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        cols = [c.lower() for c in (r.fieldnames or [])]
        key = None
        for k in ("total_backoff_s", "backoff_s", "backoff_seconds", "backoff"):
            if k in cols:
                key = k
                break
        for row in r:
            if key:
                total += to_int(row.get(key, 0))
    return {"total_backoff_s": total}


def main():
    require_today = (os.environ.get("HC_REQUIRE_TODAY",
                     "1").lower() in {"1", "true", "yes"})
    # tolérant par défaut (infra)
    max_err_rate = float(os.environ.get("HC_MAX_ERR_RATE", "0.80"))
    max_backoff = int(os.environ.get("HC_MAX_BACKOFF_S", "600"))

    calls = latest_file("calls_summary__*.csv")
    meter = latest_file("meter_summary__*.csv")
    if not calls or not meter:
        print("[HC] Fichiers summary manquants → FAIL")
        sys.exit(1)

    if require_today:
        def is_today(p: Path) -> bool:
            try:
                ymd = p.stem.split("__")[-1]
                d = datetime.strptime(ymd, "%Y%m%d").date()
                return d == TODAY
            except Exception:
                return False
        if not (is_today(calls) and is_today(meter)):
            print("[HC] Pas de fichiers du jour (suffixe YYYYMMDD) → FAIL")
            sys.exit(1)

    k_calls = read_calls_summary(calls)
    k_meter = read_meter_summary(meter)

    total = max(1, k_calls["total_calls"])
    err_rate = (k_calls["err_4xx"] + k_calls["err_5xx"]) / total
    backoff = k_meter["total_backoff_s"]

    print(
        f"[HC] total_calls={total} err_rate={err_rate:.1%} backoff_s={backoff}")

    ok = True
    if err_rate > max_err_rate:
        print(f"[HC] ERR_RATE>{max_err_rate:.0%} → FAIL")
        ok = False
    if backoff > max_backoff:
        print(f"[HC] BACKOFF_S>{max_backoff} → FAIL")
        ok = False

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
