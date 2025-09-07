from app.normalize import normalize_daily
from app.callmeter import log_call, CallBudget, METER_PATH
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
from typing import Optional
import warnings
warnings.filterwarnings(
    "ignore",
    message="Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated"
)

# ====== Config ======
if os.getenv("OUTDIR"):
    BASEDIR = Path(os.getenv("OUTDIR"))
else:
    BASEDIR = Path("/data")  # par défaut : ./data dans le projet

PROCESSED_DIR = BASEDIR / "processed"
LOGSDIR = BASEDIR / "logs"
CONFIGDIR = BASEDIR / "config"

for d in (PROCESSED_DIR, LOGSDIR, CONFIGDIR):
    d.mkdir(parents=True, exist_ok=True)

# Fichiers uniques
TOPICS_ALL_PATH = PROCESSED_DIR / "topics_all.csv"
CALLS_ALL_PATH = LOGSDIR / "calls_all.csv"

GEO = os.getenv("GT_GEO", "FR")
MAX_CALLS = int(os.getenv("GT_MAX_CALLS", "3"))
RUN_ID = os.getenv("RUN_ID", str(uuid.uuid4())[:8])

# délais d’attente (élargis)
SLEEP_MIN = 15
SLEEP_MAX = 45

BUDGET = CallBudget(max_calls=MAX_CALLS, run_id=RUN_ID)
pytrends = TrendReq(hl="fr-FR", tz=0)


def _safe_build(topic: str, timeframe: str, phase: str) -> bool:
    """Un seul appel à build_payload, abandon immédiat si erreur."""
    try:
        BUDGET.hit()
        pytrends.build_payload([topic], timeframe=timeframe, geo=GEO)
        log_call(RUN_ID, phase, topic, timeframe,
                 GEO, 1, "ok", "", CALLS_ALL_PATH)
        sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
        return True
    except pt_exceptions.TooManyRequestsError:
        log_call(RUN_ID, phase, topic, timeframe, GEO, 1, "429",
                 "TooManyRequests(build)", CALLS_ALL_PATH)
        print("[ERR] build_payload: 429 Too Many Requests → abandon immédiat")
        return False
    except Exception as e:
        log_call(RUN_ID, phase, topic, timeframe, GEO, 1, "error",
                 f"build:{type(e).__name__}: {e}", CALLS_ALL_PATH)
        print(f"[ERR] build_payload: {e} → abandon immédiat")
        return False


def _safe_interest_over_time(topic: str, timeframe: str, phase: str) -> Optional[pd.DataFrame]:
    """Un seul appel à interest_over_time, abandon immédiat si erreur."""
    try:
        BUDGET.hit()
        df = pytrends.interest_over_time()
        log_call(RUN_ID, phase + ":fetch", topic, timeframe,
                 GEO, 1, "ok", "", CALLS_ALL_PATH)
        sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
        return df
    except pt_exceptions.TooManyRequestsError:
        log_call(RUN_ID, phase + ":fetch", topic, timeframe, GEO,
                 1, "429", "TooManyRequests(fetch)", CALLS_ALL_PATH)
        print("[ERR] interest_over_time: 429 Too Many Requests → abandon immédiat")
        return None
    except Exception as e:
        log_call(RUN_ID, phase + ":fetch", topic, timeframe, GEO, 1,
                 "error", f"fetch:{type(e).__name__}: {e}", CALLS_ALL_PATH)
        print(f"[ERR] interest_over_time: {e} → abandon immédiat")
        return None


def _write_daily(topic: str):
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

    # Append dans topics_all.csv
    file_exists = TOPICS_ALL_PATH.exists()
    df_norm["topic"] = topic
    df_norm["ts_utc_extraction"] = datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%S")
    df_norm.to_csv(
        TOPICS_ALL_PATH,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8"
    )
    print(f"[OK] daily → {TOPICS_ALL_PATH} (+{len(df_norm)} lignes)")


def main():
    ap = argparse.ArgumentParser(
        description="Collecte Google Trends — daily only, multi-topics")
    ap.add_argument("--topics-file", default=str(CONFIGDIR / "topics.txt"),
                    help="Fichier listant les topics (un par ligne)")
    args = ap.parse_args()

    topics_path = Path(args.topics_file)
    if not topics_path.exists():
        print(f"[ERR] Fichier topics introuvable: {topics_path}")
        return

    topics = [line.strip() for line in topics_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]

    for topic in topics:
        _write_daily(topic)

    print(f"[METER] calls={BUDGET.count} (voir {METER_PATH})")


if __name__ == "__main__":
    main()
