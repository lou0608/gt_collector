# app/daily_top_year.py
import time
import random
from pathlib import Path
import pandas as pd
from pytrends.request import TrendReq
import pytz
from datetime import timezone
from app.config import KEYWORDS, GEO

OUTDIR = Path("/data")
OUTFILE = OUTDIR / "days_top_year.csv"

RETRIES = 5
BASE_BACKOFF = 6.0
JITTER = (0.6, 1.6)
PAUSE_BETWEEN_REQ = (1.0, 2.0)
BATCH_SIZE = 3  # pytrends supporte 5 requêtes comparées

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
                f"[WARN] daily build_payload ({attempt}/{RETRIES}) kws={kws}: {e}")
            if attempt < RETRIES:
                _with_backoff(attempt)
    return False


def _append_csv(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists()
    df.to_csv(path, mode="a", index=False, header=header, encoding="utf-8-sig")


def daily_12m_all(pytrends: TrendReq) -> pd.DataFrame:
    """Télécharge le daily pour tous les mots-clés (en batchs) et renvoie ts, keyword, index."""
    parts = []
    kws = [k.strip() for k in KEYWORDS]
    for i in range(0, len(kws), BATCH_SIZE):
        batch = kws[i:i+BATCH_SIZE]
        _sleep_small()
        if not _safe_build(pytrends, batch, "today 12-m", GEO):
            continue
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            continue
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "ts"})
        df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(timezone.utc)
        # melt sur les colonnes des keywords de ce batch
        sub = df.melt(id_vars=["ts"], value_vars=batch,
                      var_name="keyword", value_name="index")
        parts.append(sub)
    if not parts:
        return pd.DataFrame()
    all_df = pd.concat(parts, ignore_index=True)
    # nettoie keywords (espaces/casse) pour fusion robuste
    all_df["keyword"] = all_df["keyword"].astype(str).str.strip()
    return all_df


def main():
    pytrends = TrendReq(hl="fr-FR", tz=0)

    all_daily = daily_12m_all(pytrends)
    if all_daily.empty:
        print("[WARN] daily: aucune donnée reçue (429 persistant ?).")
        # écrire un fichier vide pour ne pas casser les consumers
        pd.DataFrame(columns=["date", "keyword", "daily_index", "rank", "data_quality_status"]).to_csv(
            OUTFILE, index=False, encoding="utf-8-sig"
        )
        return

    # date locale pour affichage
    all_daily["date"] = all_daily["ts"].dt.tz_convert(
        paris_tz).dt.strftime("%d-%m-%Y")
    # top par (keyword) sur 12 mois : conserve ex aequo
    all_daily.rename(columns={"index": "daily_index"}, inplace=True)
    max_by_kw = (all_daily.groupby("keyword")["daily_index"].transform("max"))
    top = all_daily.loc[all_daily["daily_index"] ==
                        max_by_kw, ["date", "keyword", "daily_index"]].copy()
    top["rank"] = 1
    top["data_quality_status"] = "ok"
    top.sort_values(["keyword", "date"], inplace=True)

    _append_csv(OUTFILE, top)
    print(f"[OK] daily top days → {OUTFILE} ({len(top)} lignes)")


if __name__ == "__main__":
    main()
