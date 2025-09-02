from __future__ import annotations
import csv
import os
from pathlib import Path
from datetime import datetime
from collections import Counter

# ====== Config ======
# /data est monté par Docker ; sur GitHub Actions → ./data
if os.getenv("GITHUB_ACTIONS") == "true":
    DATA = Path("data")
else:
    DATA = Path(os.getenv("OUTDIR", "/data"))

LOGS = DATA / "logs"
METER = DATA / "gt_meter.csv"

# création sécurisée des dossiers
DATA.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)


def _latest(pattern: str, base: Path = LOGS) -> Path | None:
    files = sorted(base.glob(pattern))
    return files[-1] if files else None


def _to_int(x, default=0):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return default


def aggregate_calls() -> Path | None:
    last = _latest("calls__*.csv", LOGS)
    files = [last] if last else list(LOGS.glob("calls__*.csv"))
    if not files:
        print("[aggregate_logs] Aucun fichier calls__*.csv, on saute.")
        return None

    # date suffix
    ymd = None
    if last:
        try:
            ymd = last.stem.split("__")[-1]
            datetime.strptime(ymd, "%Y%m%d")
        except Exception:
            ymd = None
    if not ymd:
        ymd = datetime.now().strftime("%Y%m%d")

    counts = Counter()
    total = 0
    for p in files:
        with p.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                status = str(row.get("status")
                             or row.get("code") or "").strip()
                n = _to_int(row.get("count") or row.get("n") or 1, 1)
                try:
                    s = int(status)
                except Exception:
                    continue
                total += n
                if 200 <= s <= 299:
                    counts["ok_2xx"] += n
                elif 400 <= s <= 499:
                    counts["err_4xx"] += n
                elif 500 <= s <= 599:
                    counts["err_5xx"] += n

    out = DATA / f"calls_summary__{ymd}.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["total_calls", "ok_2xx", "err_4xx", "err_5xx"]
        )
        w.writeheader()
        w.writerow({
            "total_calls": total,
            "ok_2xx": counts["ok_2xx"],
            "err_4xx": counts["err_4xx"],
            "err_5xx": counts["err_5xx"],
        })
    print(f"[OK] Résumé appels → {out} (1 lignes)")
    return out


def aggregate_meter() -> Path | None:
    if not METER.exists():
        # tente data/logs/meter.csv si présent
        alt = LOGS / "meter.csv"
        if alt.exists():
            meter_path = alt
        else:
            print("[INFO] meter introuvable → utilisation de data/gt_meter.csv")
            meter_path = METER
        if not meter_path.exists():
            print("[aggregate_logs] Pas de meter, on saute.")
            return None
    else:
        meter_path = METER

    total_backoff = 0
    with meter_path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        cols = [c.lower() for c in (r.fieldnames or [])]
        key = None
        for k in ["total_backoff_s", "backoff_s", "backoff_seconds", "backoff"]:
            if k in cols:
                key = k
                break
        for row in r:
            if key:
                total_backoff += _to_int(row.get(key, 0))

    ymd = datetime.now().strftime("%Y%m%d")
    out = DATA / f"meter_summary__{ymd}.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["total_backoff_s"])
        w.writeheader()
        w.writerow({"total_backoff_s": total_backoff})
    print(f"[OK] Résumé meter → {out} (1 lignes)")
    return out


def main():
    aggregate_calls()
    aggregate_meter()


if __name__ == "__main__":
    main()
