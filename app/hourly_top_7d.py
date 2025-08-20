# app/hourly_top_7d.py
import time
import random
from pathlib import Path
import pandas as pd
from pytrends.request import TrendReq
import pytz
from datetime import timezone
from app.config import KEYWORDS, GEO

OUTDIR = Path("/data")
OUTFILE = OUTDIR / "hours_top_7d.csv"

RETRIES = 5
BASE_BACKOFF = 6.0
JITTER = (0.6, 1.6)
PAUSE_BETWEEN_REQ = (1.0, 2.0)
BATCH_SIZE = 3

paris_tz = pytz.timezone("Europe/Paris")


def _sleep_small():
    time.sleep(random.uniform(*PAUSE_BETWEEN_REQ))


def _with_backoff(attempt: int):
    time.sleep(BASE_BACKOFF * (2 ** (attempt - 1)) * random.uniform(*JITTER))


def _safe_build(pytrends: TrendReq, kws, timeframe: str, geo: str) -> bool:
    for attempt in range(1, RETRIES + 1):
        try:
            pytrends.build_payload(kws, timeframe=timeframe, geo=geo)
            return True
        except Exception as e:
            print(
                f"[WARN] hourly build_payload ({attempt}/{RETRIES}) kws={kws}: {e}")
            if attempt < RETRIES:
                _with_backoff(attempt)
    return False


def _append_csv(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists()
    df.to_csv(path, mode="a", index=False, header=header, encoding="utf-8-sig")


def hourly_7d_all(pytrends: TrendReq) -> pd.DataFrame:
    """Télécharge l’horaire 7j pour tous les mots-clés (en batchs) et renvoie load_utc, keyword, index."""
    parts = []
    kws = [k.strip() for k in KEYWORDS]
    for i in range(0, len(kws), BATCH_SIZE):
        batch = kws[i:i+BATCH_SIZE]
        _sleep_small()
        if not _safe_build(pytrends, batch, "now 7-d", GEO):
            continue
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            continue
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "ts"})
        df["load_utc"] = pd.to_datetime(df["ts"]).dt.tz_localize(timezone.utc)
        sub = df.melt(id_vars=["load_utc"], value_vars=batch,
                      var_name="keyword", value_name="index")
        parts.append(sub)
    if not parts:
        return pd.DataFrame()
    all_df = pd.concat(parts, ignore_index=True)
    all_df["keyword"] = all_df["keyword"].astype(str).str.strip()
    # colonnes locales
    local_dt = all_df["load_utc"].dt.tz_convert(paris_tz)
    all_df["date"] = local_dt.dt.strftime("%d-%m-%Y")
    all_df["heure"] = local_dt.dt.strftime("%H:%M")
    return all_df


def main():
    pytrends = TrendReq(hl="fr-FR", tz=0)

    all_hourly = hourly_7d_all(pytrends)
    if all_hourly.empty:
        print("[WARN] hourly: aucune donnée reçue (429 persistant ?).")
        pd.DataFrame(columns=[
            "date", "heure", "keyword", "hourly_index", "load_utc", "data_quality_status"
        ]).to_csv(OUTFILE, index=False, encoding="utf-8-sig")
        return

    # meilleur point (jour+heure) par mot-clé sur 7 jours
    all_hourly.rename(columns={"index": "hourly_index"}, inplace=True)
    idx = all_hourly.groupby("keyword")["hourly_index"].idxmax()
    top = all_hourly.loc[idx, ["date", "heure",
                               "keyword", "hourly_index", "load_utc"]].copy()
    top["data_quality_status"] = "ok"
    top.sort_values(["keyword", "load_utc"], inplace=True)

    _append_csv(OUTFILE, top)
    print(f"[OK] hourly top 7d → {OUTFILE} ({len(top)} lignes)")


if __name__ == "__main__":
    main()
