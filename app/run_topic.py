# app/run_topic.py
import os
import uuid
import random
import argparse
from time import sleep
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import pytz
from pytrends.request import TrendReq
# pour capturer TooManyRequestsError
from pytrends import exceptions as pt_exceptions

from app.callmeter import log_call, CallBudget, METER_PATH
from app.normalize import normalize_daily, normalize_hourly

# ====== Config ======
# /data est monté par Docker ; on écrit sous /data/raw/{daily|hourly}
BASEDIR = Path(os.getenv("OUTDIR", "/data"))
RAWDIR = BASEDIR / "raw"
DAILYDIR = RAWDIR / "daily"
HOURLYDIR = RAWDIR / "hourly"
for d in (RAWDIR, DAILYDIR, HOURLYDIR):
    d.mkdir(parents=True, exist_ok=True)

GEO = os.getenv("GT_GEO", "FR")
MAX_CALLS = int(os.getenv("GT_MAX_CALLS", "3"))  # ← au moins 2 (build + fetch)
RUN_ID = os.getenv("RUN_ID", str(uuid.uuid4())[:8])

# Pré-jitter optionnel avant un build_payload (en secondes)
PREJITTER_MIN = float(os.getenv("GT_PREJITTER_MIN", "3"))
PREJITTER_MAX = float(os.getenv("GT_PREJITTER_MAX", "12"))

BUDGET = CallBudget(max_calls=MAX_CALLS, run_id=RUN_ID)
# tz=0 → index UTC pour les timestamps pytrends
pytrends = TrendReq(hl="fr-FR", tz=0)


def _slugify(label: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-").replace("--", "-")


def _safe_build(topic_mid: str, timeframe: str, phase: str) -> bool:
    """
    build_payload avec :
      - budget,
      - journal,
      - retries/backoff exponentiel + jitter,
      - gestion explicite des 429.
    """
    RETRIES = int(os.getenv("GT_RETRIES", "6"))
    BASE_BACKOFF = float(os.getenv("GT_BASE_BACKOFF", "20.0"))  # secondes

    # Pré-jitter (éviter d'arriver synchro avec d'autres jobs)
    pre_sleep = random.uniform(PREJITTER_MIN, PREJITTER_MAX)
    sleep(pre_sleep)

    kws = [topic_mid]  # 1 topic par run
    for attempt in range(1, RETRIES + 1):
        try:
            BUDGET.hit()
            pytrends.build_payload(kws, timeframe=timeframe, geo=GEO)
            log_call(RUN_ID, phase, topic_mid,
                     timeframe, GEO, attempt, "ok", "")
            # petit jitter après succès pour espacer les appels suivants
            sleep(random.uniform(8, 20))
            return True

        except pt_exceptions.TooManyRequestsError:
            log_call(RUN_ID, phase, topic_mid, timeframe, GEO,
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
            log_call(RUN_ID, phase, topic_mid, timeframe, GEO,
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


def _safe_interest_over_time(topic_mid: str, timeframe: str, phase: str) -> pd.DataFrame | None:
    """
    interest_over_time() avec :
      - budget,
      - journal détaillé,
      - retries/backoff exponentiel + jitter,
      - gestion explicite des 429.
    """
    RETRIES = int(os.getenv("GT_RETRIES", "6"))
    BASE_BACKOFF = float(os.getenv("GT_BASE_BACKOFF", "20.0"))  # secondes

    for attempt in range(1, RETRIES + 1):
        try:
            BUDGET.hit()
            df = pytrends.interest_over_time()
            # Succès : on log et on retourne
            log_call(RUN_ID, phase + ":fetch", topic_mid,
                     timeframe, GEO, attempt, "ok", "")
            # petit jitter pour éviter d'enchaîner trop vite
            sleep(random.uniform(5, 12))
            return df

        except pt_exceptions.TooManyRequestsError:
            log_call(RUN_ID, phase + ":fetch", topic_mid, timeframe,
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
            log_call(RUN_ID, phase + ":fetch", topic_mid, timeframe,
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


# ---------- DAILY (fenêtre 2024) ----------
def _write_daily_2024(topic_mid: str, topic_label: str, topic_slug: str, run_date: str):
    phase = "daily_2024"
    tf = "2024-01-01 2024-12-31"
    if not _safe_build(topic_mid, tf, phase):
        print(f"[WARN] daily_2024 KO ({topic_label})")
        return

    df = _safe_interest_over_time(topic_mid, tf, phase)
    if df is None or df.empty:
        print(f"[INFO] Aucune donnée daily_2024 pour {topic_label}")
        return

    # Normalisation → schéma: date,value,topic_mid,topic_label,geo,window,created_at
    df_norm = normalize_daily(
        df=df,
        topic_mid=topic_mid,
        topic_label=topic_label,
        geo=GEO,
        window="2024",
    )

    out = DAILYDIR / f"daily_2024__{topic_slug}__{run_date}.csv"
    df_norm.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] daily_2024 → {out} ({len(df_norm)} lignes)")


# Utilitaire : détecter s'il existe déjà un bootstrap horaire pour ce slug
def _bootstrap_exists(topic_slug: str) -> bool:
    return any(HOURLYDIR.glob(f"hourly_7d__{topic_slug}__*.csv"))


# ---------- HOURLY commun (fenêtre now 7-d systématique) ----------
def _write_hourly_common(topic_mid: str, topic_label: str, topic_slug: str, run_date: str, phase: str, filter_yesterday: bool = False):
    tf = "now 7-d"
    if not _safe_build(topic_mid, tf, phase):
        print(f"[WARN] {phase} KO ({topic_label})")
        return

    df = _safe_interest_over_time(topic_mid, tf, phase)
    if df is None or df.empty:
        print(f"[INFO] Aucune donnée {phase} pour {topic_label}")
        return

    # Normalisation → schéma: datetime_paris,date,hour,value,topic_mid,topic_label,geo,window,created_at
    df_norm = normalize_hourly(
        df=df,
        topic_mid=topic_mid,
        topic_label=topic_label,
        geo=GEO,
        window="now 7-d",
    )

    # Optionnel : si mode "yesterday", on ne garde que la journée d'hier (Europe/Paris)
    if filter_yesterday and not df_norm.empty:
        paris = pytz.timezone("Europe/Paris")
        yesterday = datetime.now(paris).date() - timedelta(days=1)
        df_norm = df_norm[df_norm["date"] == yesterday.strftime("%Y-%m-%d")]
        if df_norm.empty:
            print(
                f"[INFO] Pas de lignes horaires pour 'hier' ({yesterday}) sur {topic_label}")
            return

    out = HOURLYDIR / f"hourly_7d__{topic_slug}__{run_date}.csv"
    df_norm.to_csv(out, index=False, encoding="utf-8")
    print(f"[OK] {phase} → {out} ({len(df_norm)} lignes)")


def _write_hourly_bootstrap_7d(topic_mid: str, topic_label: str, topic_slug: str, run_date: str):
    _write_hourly_common(topic_mid, topic_label, topic_slug, run_date,
                         phase="hourly_7d_bootstrap", filter_yesterday=False)


def _write_hourly_yesterday(topic_mid: str, topic_label: str, topic_slug: str, run_date: str):
    _write_hourly_common(topic_mid, topic_label, topic_slug,
                         run_date, phase="hourly_yesterday", filter_yesterday=True)


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(
        description="POC Google Trends — 1 topic par run")
    ap.add_argument("--topic-mid", required=True,
                    help="ID topic (MID), ex: /m/01wgr")
    ap.add_argument("--topic-label", required=True,
                    help="Label lisible, ex: cardiologie")

    # Paramètres horaires
    ap.add_argument("--only-hourly", action="store_true",
                    help="Exécute uniquement l'horaire (pas de daily 2024)")
    ap.add_argument(
        "--hourly-mode",
        choices=["auto", "bootstrap", "yesterday"],
        default="auto",
        help="Mode horaire : auto (défaut), bootstrap, ou yesterday",
    )

    args = ap.parse_args()
    topic_mid = args.topic_mid
    topic_label = args.topic_label
    topic_slug = _slugify(topic_label)

    # Datestamp d’exécution en Europe/Paris pour les noms de fichiers
    run_date = datetime.now(pytz.timezone("Europe/Paris")).strftime("%Y%m%d")

    if args.only_hourly:
        # MODE HORAIRE SEUL
        if args.hourly_mode == "bootstrap":
            _write_hourly_bootstrap_7d(
                topic_mid, topic_label, topic_slug, run_date)
        elif args.hourly_mode == "yesterday":
            _write_hourly_yesterday(
                topic_mid, topic_label, topic_slug, run_date)
        else:  # auto
            if not _bootstrap_exists(topic_slug):
                _write_hourly_bootstrap_7d(
                    topic_mid, topic_label, topic_slug, run_date)
            else:
                _write_hourly_yesterday(
                    topic_mid, topic_label, topic_slug, run_date)
    else:
        # MODE COMPLET : daily + horaire (auto)
        _write_daily_2024(topic_mid, topic_label, topic_slug, run_date)
        if not _bootstrap_exists(topic_slug):
            _write_hourly_bootstrap_7d(
                topic_mid, topic_label, topic_slug, run_date)
        else:
            _write_hourly_yesterday(
                topic_mid, topic_label, topic_slug, run_date)

    # Monitoring fin de run
    print(f"[METER] calls={BUDGET.count} (voir {METER_PATH})")


if __name__ == "__main__":
    main()
