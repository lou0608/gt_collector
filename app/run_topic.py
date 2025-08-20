# app/run_topic.py
import os
import uuid
import random
import argparse
from time import sleep
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
import pandas as pd
from pytrends.request import TrendReq

from app.callmeter import log_call, CallBudget, METER_PATH

# ====== Config ======
OUTDIR = Path(os.getenv("OUTDIR", "/data"))
OUTDIR.mkdir(parents=True, exist_ok=True)

GEO = os.getenv("GT_GEO", "FR")
MAX_CALLS = int(os.getenv("GT_MAX_CALLS", "5"))  # strict comme validé
RUN_ID = os.getenv("RUN_ID", str(uuid.uuid4())[:8])

BUDGET = CallBudget(max_calls=MAX_CALLS)
pytrends = TrendReq(hl="fr-FR", tz=0)  # tz=0 → index UTC


def _slugify(label: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-").replace("--", "-")


def _safe_build(topic_mid: str, timeframe: str, phase: str) -> bool:
    """Wrapper build_payload avec budget, journal, retries/backoff, jitter."""
    RETRIES = 3
    BASE_BACKOFF = 10.0
    kws = [topic_mid]  # 1 topic par run → batch size = 1
    for attempt in range(1, RETRIES + 1):
        try:
            BUDGET.hit()
            pytrends.build_payload(kws, timeframe=timeframe, geo=GEO)
            log_call(RUN_ID, phase, topic_mid,
                     timeframe, GEO, attempt, "ok", "")
            sleep(random.uniform(6, 12))  # jitter
            return True
        except Exception as e:
            log_call(RUN_ID, phase, topic_mid, timeframe,
                     GEO, attempt, "error", str(e))
            if attempt < RETRIES:
                sleep(BASE_BACKOFF * (2 ** (attempt - 1)))
            else:
                return False


def _write_daily_2024(topic_mid: str, topic_label: str, topic_slug: str, run_date: str):
    phase = "daily_2024"
    tf = "2024-01-01 2024-12-31"
    if not _safe_build(topic_mid, tf, phase):
        print(f"[WARN] daily_2024 KO ({topic_label})")
        return

    df = pytrends.interest_over_time()
    if df is None or df.empty:
        print(f"[INFO] Aucune donnée daily_2024 pour {topic_label}")
        return

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    df = df.reset_index().rename(columns={"date": "date"})
    df_long = df.melt(id_vars=["date"],
                      var_name="topic_mid", value_name="value")
    # Ici, une seule colonne (topic_mid), mais on normalise quand même
    df_long["topic_label"] = topic_label
    df_long["geo"] = GEO
    df_long["run_id"] = RUN_ID
    df_long["phase"] = phase

    out = OUTDIR / f"daily_2024__{topic_slug}__{run_date}.csv"
    df_long.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] daily_2024 → {out} ({len(df_long)} lignes)")


def _bootstrap_exists(topic_slug: str) -> bool:
    # On considère "bootstrap présent" si au moins un fichier hourly_7d existe pour ce slug
    matches = list(OUTDIR.glob(f"hourly_7d__{topic_slug}__*.csv"))
    return len(matches) > 0


def _write_hourly_bootstrap_7d(topic_mid: str, topic_label: str, topic_slug: str, run_date: str):
    phase = "hourly_7d_bootstrap"
    tf = "now 7-d"
    if not _safe_build(topic_mid, tf, phase):
        print(f"[WARN] hourly_7d bootstrap KO ({topic_label})")
        return
    _write_hourly_common(topic_mid, topic_label, topic_slug, run_date,
                         phase, fname=f"hourly_7d__{topic_slug}__{run_date}.csv")


def _write_hourly_yesterday(topic_mid: str, topic_label: str, topic_slug: str, run_date: str):
    phase = "hourly_yesterday"
    # Hier en UTC (00:00→23:59), pytrends prend 'YYYY-MM-DD YYYY-MM-DD' (jours inclusifs)
    today_utc = datetime.now(timezone.utc).date()
    yesterday = today_utc - timedelta(days=1)
    tf = f"{yesterday.isoformat()} {yesterday.isoformat()}"
    if not _safe_build(topic_mid, tf, phase):
        print(f"[WARN] hourly_yesterday KO ({topic_label})")
        return
    _write_hourly_common(topic_mid, topic_label, topic_slug, run_date,
                         phase, fname=f"hourly_yesterday__{topic_slug}__{run_date}.csv")


def _write_hourly_common(topic_mid: str, topic_label: str, topic_slug: str, run_date: str, phase: str, fname: str):
    df = pytrends.interest_over_time()
    if df is None or df.empty:
        print(f"[INFO] Aucune donnée {phase} pour {topic_label}")
        return

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    # Index UTC → Europe/Paris + heure locale
    df.index = df.index.tz_localize("UTC").tz_convert("Europe/Paris")
    df["hour_local"] = df.index.hour
    df = df.reset_index().rename(columns={"date": "dt_local"})

    # Long format (1 topic)
    # La colonne du topic MID est exactement topic_mid
    df_long = df.melt(id_vars=["dt_local", "hour_local"],
                      var_name="topic_mid", value_name="value")
    df_long = df_long[df_long["topic_mid"] == topic_mid].copy()

    df_long["topic_label"] = topic_label
    df_long["geo"] = GEO
    df_long["run_id"] = RUN_ID
    df_long["phase"] = phase

    out = OUTDIR / fname
    df_long.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] {phase} → {out} ({len(df_long)} lignes)")


def main():
    ap = argparse.ArgumentParser(
        description="POC Google Trends — 1 topic par run")
    ap.add_argument("--topic-mid", required=True,
                    help="ID topic (MID), ex: /m/01wgr")
    ap.add_argument("--topic-label", required=True,
                    help="Label lisible, ex: cardiologie")
    args = ap.parse_args()

    topic_mid = args.topic_mid
    topic_label = args.topic_label
    topic_slug = _slugify(topic_label)
    run_date = datetime.now().strftime("%Y%m%d")

    # 1) Daily 2024 (toujours)
    _write_daily_2024(topic_mid, topic_label, topic_slug, run_date)

    # 2) Hourly : bootstrap 7j si pas encore fait, sinon "hier"
    if not _bootstrap_exists(topic_slug):
        _write_hourly_bootstrap_7d(
            topic_mid, topic_label, topic_slug, run_date)
    else:
        _write_hourly_yesterday(topic_mid, topic_label, topic_slug, run_date)

    # Monitoring fin de run
    print(f"[METER] calls={BUDGET.count} (voir {METER_PATH})")


if __name__ == "__main__":
    main()
