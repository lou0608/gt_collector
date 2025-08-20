# app/trends_postprocess.py
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import random

import pandas as pd
import pytz
from pytrends.request import TrendReq

# --- CONFIG ---
KEYWORDS = [
    "Cardiologie",
    "Maladies cardiaques",
    "Infarctus du myocarde",
    "Hypertension artérielle",
    "Arythmie",
    "Cholestérol",
    "Angine de poitrine",
    "Échocardiographie",
    "Stent coronaire",
    "Prévention cardiovasculaire",
]
GEO = "FR"
OUTDIR = Path("/data")
OUTFILE = OUTDIR / "trends_filtered.csv"
RAW_DAILY = OUTDIR / "trends_daily.csv"   # debug : daily sur 12 mois
# debug : concat des fenêtres horaires consultées
RAW_HOURLY = OUTDIR / "trends_hourly.csv"

# Seuil
DAILY_THRESHOLD = 80

# Anti-throttling
RETRIES = 4
BASE_BACKOFF = 3.0   # secondes
JITTER = (0.6, 1.4)  # multiplicateur aléatoire
PAUSE_BETWEEN_REQ = (1.0, 2.5)  # petite pause entre requêtes

paris_tz = pytz.timezone("Europe/Paris")


def _sleep_small():
    time.sleep(random.uniform(*PAUSE_BETWEEN_REQ))


def _with_backoff(attempt: int):
    delay = BASE_BACKOFF * (2 ** (attempt - 1)) * random.uniform(*JITTER)
    time.sleep(delay)


def _safe_build(pytrends: TrendReq, kw: str, timeframe: str, geo: str) -> bool:
    for attempt in range(1, RETRIES + 1):
        try:
            pytrends.build_payload([kw], timeframe=timeframe, geo=geo)
            return True
        except Exception as e:
            print(
                f"[WARN] build_payload failed ({attempt}/{RETRIES}) kw='{kw}' tf='{timeframe}': {e}")
            if attempt < RETRIES:
                _with_backoff(attempt)
    return False


def get_daily_last_12m(pytrends: TrendReq, keyword: str) -> pd.DataFrame:
    """
    Récupère le daily sur 12 mois (1 seule requête) et renvoie un DF avec:
    columns: date(naive UTC), keyword, index
    """
    tf = "today 12-m"  # daily
    ok = _safe_build(pytrends, keyword, tf, GEO)
    if not ok:
        return pd.DataFrame()

    df = pytrends.interest_over_time()
    if df is None or df.empty:
        return pd.DataFrame()

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])
    df = df.reset_index().rename(columns={"date": "ts"})
    df["keyword"] = keyword
    df.rename(columns={keyword: "index"}, inplace=True)
    # ts renvoyé en daily (naive) -> localise UTC pour cohérence
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(timezone.utc)
    return df[["ts", "keyword", "index"]]


def get_hourly_window(pytrends: TrendReq, keyword: str, start_utc: datetime, end_utc: datetime) -> pd.DataFrame:
    """
    Fenêtre horaire (<= 7 jours). Renvoie colonnes: load_utc, keyword, index, date, heure
    """
    timeframe = f"{start_utc.strftime('%Y-%m-%d')} {end_utc.strftime('%Y-%m-%d')}"
    ok = _safe_build(pytrends, keyword, timeframe, GEO)
    if not ok:
        return pd.DataFrame()

    df = pytrends.interest_over_time()
    if df is None or df.empty:
        return pd.DataFrame()

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])
    df = df.reset_index().rename(columns={"date": "ts"})
    df.rename(columns={keyword: "index"}, inplace=True)

    # load_utc = ts en UTC
    df["load_utc"] = pd.to_datetime(df["ts"]).dt.tz_localize(timezone.utc)

    local_dt = df["load_utc"].dt.tz_convert(paris_tz)
    df["date"] = local_dt.dt.strftime("%d-%m-%Y")
    df["heure"] = local_dt.dt.strftime("%H:%M")
    df["keyword"] = keyword

    return df[["date", "heure", "keyword", "index", "load_utc"]]


def run_trends_postprocess():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    pytrends = TrendReq(hl="fr-FR", tz=0)

    # -------- PHASE A: DAILY 12 mois --------
    daily_parts = []
    for kw in KEYWORDS:
        _sleep_small()
        d = get_daily_last_12m(pytrends, kw)
        if not d.empty:
            daily_parts.append(d)

    if not daily_parts:
        print("[WARN] PHASE A: aucune donnée daily.")
        return

    daily = pd.concat(daily_parts, ignore_index=True)
    daily.to_csv(RAW_DAILY, index=False, encoding="utf-8-sig")  # debug

    # Jour local (Europe/Paris) pour filtrer par DATE (pas par timestamp UTC)
    daily["day_local"] = daily["ts"].dt.tz_convert(
        paris_tz).dt.strftime("%d-%m-%Y")

    # --- Jours candidats: index daily > threshold ---
    cands = daily.loc[daily["index"] > DAILY_THRESHOLD,
                      ["keyword", "day_local"]].drop_duplicates()

    if cands.empty:
        print("[INFO] Aucun jour > 80 détecté sur 12 mois. Fichier résultat vide.")
        pd.DataFrame(columns=["date", "heure", "keyword", "index", "load_utc"]).to_csv(
            OUTFILE, index=False, encoding="utf-8-sig")
        return

    # -------- PHASE B: HOURLY autour des jours candidats --------
    hourly_parts = []
    for kw, day_local in cands.itertuples(index=False):
        # Reconstruire la date UTC min/max de la fenetre 7j centrée sur le jour
        # On parse day_local comme date locale Europe/Paris à 00:00
        day_dt_local = paris_tz.localize(
            datetime.strptime(day_local, "%d-%m-%Y"))
        # Fenêtre [J-3, J+4] => 7 jours
        start_local = (day_dt_local - timedelta(days=3)
                       ).astimezone(timezone.utc)
        end_local = (day_dt_local + timedelta(days=4)).astimezone(timezone.utc)

        # petite pause anti-throttling
        _sleep_small()

        win = get_hourly_window(pytrends, kw, start_local, end_local)
        if win.empty:
            continue

        # ne garder que le jour voulu (en local)
        mask_day = (win["date"] == day_local)
        sub = win.loc[mask_day]
        if sub.empty:
            continue

        # Prendre l’heure max pour ce (kw, day_local)
        top = sub.loc[sub["index"].idxmax()]
        hourly_parts.append(top)

    if not hourly_parts:
        print("[WARN] PHASE B: aucun horaire trouvé pour les jours candidats.")
        pd.DataFrame(columns=["date", "heure", "keyword", "index", "load_utc"]).to_csv(
            OUTFILE, index=False, encoding="utf-8-sig")
        return

    hourly_df = pd.DataFrame(hourly_parts)
    # option debug
    hourly_df.to_csv(RAW_HOURLY, index=False, encoding="utf-8-sig")

    # Résultat final demandé
    result = hourly_df[["date", "heure",
                        "keyword", "index", "load_utc"]].copy()
    result.sort_values(["keyword", "load_utc"], inplace=True)
    result.drop_duplicates(
        subset=["keyword", "load_utc"], keep="first", inplace=True)

    result.to_csv(OUTFILE, index=False, encoding="utf-8-sig")
    print(f"[OK] {len(result)} lignes écrites → {OUTFILE}")


if __name__ == "__main__":
    run_trends_postprocess()
