import uuid
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
from pytrends.request import TrendReq
from app.config import KEYWORDS, GEO, TIMEFRAME, CSV_PATH, MON_PATH


def log_run(run_id, start_ts, status, rows, error_msg=""):
    Path(MON_PATH).parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame([{
        "run_id": run_id,
        "start_ts": start_ts.isoformat(timespec="seconds"),
        "end_ts": datetime.utcnow().isoformat(timespec="seconds"),
        "status": status, "rows": rows, "error_msg": error_msg
    }])
    header = not Path(MON_PATH).exists()
    new.to_csv(MON_PATH, mode="a", index=False, header=header)


def collect(kw_list):
    pytrends = TrendReq(hl="fr-FR", tz=0)
    pytrends.build_payload(kw_list, timeframe=TIMEFRAME, geo=GEO)
    df = pytrends.interest_over_time()
    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])
    df = df.reset_index().rename(columns={"date": "timestamp"})
    df = df.melt(id_vars=["timestamp"], var_name="keyword", value_name="index")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["load_utc"] = datetime.utcnow().isoformat(timespec="seconds")
    return df


if __name__ == "__main__":
    run_id = str(uuid.uuid4())[:8]
    start_ts = datetime.utcnow()
    rows = 0
    try:
        df = collect(KEYWORDS)
        assert len(df) > 0, "Aucune ligne retournée"
        assert df["index"].between(0, 100).all(), "Indice hors plage 0..100"
        Path(CSV_PATH).parent.mkdir(parents=True, exist_ok=True)
        header = not Path(CSV_PATH).exists()
        df.to_csv(CSV_PATH, mode="a", index=False, header=header)
        rows = len(df)
        log_run(run_id, start_ts, "SUCCESS", rows)
        print(f"[OK] {rows} lignes écrites → {CSV_PATH}")

        # === AJOUT : post-traitement Google Trends complet ===
        try:
            from app.trends_postprocess import run_trends_postprocess
            run_trends_postprocess()
        except Exception as e:
            print(f"[ERROR] trends_postprocess: {e}")

        sys.exit(0)
    except Exception as e:
        log_run(run_id, start_ts, "FAILED", rows, error_msg=str(e))
        print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(1)
