# app/run_topic.py
import os
import uuid
import random
import argparse
from time import sleep
from pathlib import Path
from datetime import datetime
import pandas as pd
import pytz
from pytrends.request import TrendReq
from pytrends import exceptions as pt_exceptions
from typing import Optional  # ✅ pour compatibilité Python 3.9

from app.callmeter import log_call, CallBudget, METER_PATH
from app.normalize import normalize_daily

# ====== Config ======
if os.getenv("GITHUB_ACTIONS") == "true":
    BASEDIR = Path("data")
else:
    BASEDIR = Path(os.getenv("OUTDIR", "/data"))

RAWDIR = BASEDIR / "raw"
DAILYDIR = RAWDIR / "daily"
LOGSDIR = BASEDIR / "logs"

for d in (RAWDIR, DAILYDIR, LOGSDIR):
    d.mkdir(parents=True, exist_ok=True)

GEO = os.getenv("GT_GEO", "FR")
MAX_CALLS = int(os.getenv("GT_MAX_CALLS", "3"))
RUN_ID = os.getenv("RUN_ID", str(uuid.uuid4())[:8])

PREJITTER_MIN = float(os.getenv("GT_PREJITTER_MIN", "3"))
PREJITTER_MAX = float(os.getenv("GT_PREJITTER_MAX", "12"))

BUDGET = CallBudget(max_calls=MAX_CALLS, run_id=RUN_ID)
pytrends = TrendReq(hl="fr-FR", tz=0)


def _slugify(label: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-").replace("--", "-")


def _safe_build(topic: str, timeframe: str, phase: str) -> bool:
    RETRIES = int(os.getenv("GT_RETRIES", "6"))
    BASE_BACKOFF = float(os.getenv("GT_BASE_BACKOFF", "20.0"))

    pre_sleep = random.uniform(PREJITTER_MIN, PREJITTER_MAX)
    sleep(pre_sleep)

    kws = [topic]
    for attempt in range(1, RETRIES + 1):
        try:
            BUDGET.hit()
            pytrends.build_payload(kws, timeframe=timeframe, geo=GEO)
            log_call(RUN_ID, phase, topic, timeframe, GEO, attempt, "ok", "")
            sleep(random.uniform(8, 20))
            return True
        except pt_exceptions.TooManyRequestsError:
            log_call(RUN_ID, phase, topic, timeframe, GEO,
                     attempt, "429", "TooManyRequests(build)")
            if attempt < RETRIES:
                sleep_time = BASE_BACKOFF * \
                    (2 ** (attempt - 1)) + random.uniform(5, 20)
                print(
                    f"[429] build_payload: backoff {sleep_time:.1f}s (tentative {attempt}/{RETRIES})…")
                sleep(sleep_time)
                continue
            else:
                print("[ERR] build_payload: abandon après multiples 429")
                return False
        except Exception as e:
            log_call(RUN_ID, phase, topic, timeframe, GEO,
                     attempt, "error", f"build:{type(e).__name__}: {e}")
            if attempt < RETRIES:
                sleep_time = (BASE_BACKOFF / 2) * \
                    (2 ** (attempt - 1)) + random.uniform(3, 10)
                print(
                    f"[WARN] build_payload {type(e).__name__}: backoff {sleep_time:.1f}s (tentative {attempt}/{RETRIES})…")
                sleep(sleep_time)
                continue
            else:
                print(f"[ERR] build_payload: abandon après erreurs : {e}")
                return False


def _safe_interest_over_time(topic: str, timeframe: str, phase: str) -> Optional[pd.DataFrame]:
    RETRIES = int(os.getenv("GT_RETRIES", "6"))
    BASE_BACKOFF = float(os.getenv("GT_BASE_BACKOFF", "20.0"))

    for attempt in range(1, RETRIES + 1):
        try:
            BUDGET.hit()
            df = pytrends.interest_over_time()
            log_call(RUN_ID, phase + ":fetch", topic,
                     timeframe, GEO, attempt, "ok", "")
            sleep(random.uniform(5, 12))
            return df
        except pt_exceptions.TooManyRequestsError:
            log_call(RUN_ID, phase + ":fetch", topic, timeframe,
                     GEO, attempt, "429", "TooManyRequests(fetch)")
            if attempt < RETRIES:
                sleep_time = BASE_BACKOFF * \
                    (2 ** (attempt - 1)) + random.uniform(5, 20)
                print(
                    f"[429] interest_over_time: backoff {sleep_time:.1f}s (tentative {attempt}/{RETRIES})…")
                sleep(sleep_time)
                continue
            else:
                print("[ERR] interest_over_time: abandon après multiples 429")
                return None
        except Exception as e:
            log_call(RUN_ID, phase + ":fetch", topic, timeframe,
                     GEO, attempt, "error", f"fetch:{type(e).__name__}: {e}")
            if attempt < RETRIES:
                sleep_time = (BASE_BACKOFF / 2) * \
                    (2 ** (attempt - 1)) + random.uniform(3, 10)
                print(
                    f"[WARN] interest_over_time {type(e).__name__}: backoff {sleep_time:.1f}s (tentative {attempt}/{RETRIES})…")
                sleep(sleep_time)
                continue
            else:
                print(f"[ERR] interest_over_time: abandon après erreurs : {e}")
                return None


def _write_daily(topic: str, run_date: str):
    phase = "daily"
    tf = "today 5-y"
    if not _safe_build(topic, tf, phase):
        print(f"[WARN] daily KO ({topic})")
        return

    df = _safe_interest_over_time(topic, tf, phase)
    if df is None or df.empty:
        print(f"[INFO] Aucune donnée daily pour {topic}")
        return

    df_norm = normalize_daily(
        df=df,
        topic_mid=topic,
        topic_label=topic,
        geo=GEO,
        window="5y",
    )

    slug = _slugify(topic)
    out = DAILYDIR / f"daily__{slug}__{run_date}.csv"
    df_norm.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] daily → {out} ({len(df_norm)} lignes)")


def main():
    ap = argparse.ArgumentParser(
        description="Collecte Google Trends — daily only, multi-topics")
    ap.add_argument("--topics-file", default="config/topics.txt",
                    help="Fichier listant les topics (un par ligne)")
    args = ap.parse_args()

    run_date = datetime.now(pytz.timezone("Europe/Paris")).strftime("%Y%m%d")

    topics_path = Path(args.topics_file)
    if not topics_path.exists():
        print(f"[ERR] Fichier topics introuvable: {topics_path}")
        return

    topics = [line.strip() for line in topics_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]

    for topic in topics:
        _write_daily(topic, run_date)

    print(f"[METER] calls={BUDGET.count} (voir {METER_PATH})")


if __name__ == "__main__":
    main()
