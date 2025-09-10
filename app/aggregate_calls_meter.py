# app/aggregate_calls_meter.py
# But : Construire 2 fichiers "append" depuis les logs existants :
#   - data/processed/calls_all.csv  (ts_utc,run_id,phase,topic_mid,timeframe,geo,attempt,status,error)
#   - data/processed/meter.csv      (ts_utc,run_id,count,max_calls)
#
# Source : data/logs/ (ex: calls__*.csv, meter*.csv)
# Idempotent : concat + dédup, colonnes normalisées, types stabilisés.

from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
import pandas as pd

EXPECTED_CALLS_COLS = ["ts_utc", "run_id", "phase",
                       "topic_mid", "timeframe", "geo", "attempt", "status", "error"]
EXPECTED_METER_COLS = ["ts_utc", "run_id", "count", "max_calls"]


def _outdir() -> Path:
    return Path(os.getenv("OUTDIR", "data")).resolve()


def _mk(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _first_present(dcols, *cands):
    lower = {c.lower(): c for c in dcols}
    for cand in cands:
        if cand in lower:
            return lower[cand]
    return None


def _normalize_ts_to_utc_str(series):
    ts = pd.to_datetime(series, errors="coerce", utc=True)
    return ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_calls_types(out: pd.DataFrame) -> pd.DataFrame:
    # Types stables : strings pour le texte, Int64 pour attempt
    text_cols = ["ts_utc", "run_id", "phase", "topic_mid",
                 "timeframe", "geo", "status", "error"]
    for c in text_cols:
        if c in out.columns:
            out[c] = out[c].astype("string")
    if "attempt" in out.columns:
        out["attempt"] = pd.to_numeric(
            out["attempt"], errors="coerce").astype("Int64")
    # Remplacements des NaN : vide pour textes, NA pour Int64 (restera vide en CSV)
    for c in text_cols:
        if c in out.columns:
            out[c] = out[c].fillna("")
    return out


def _coerce_meter_types(out: pd.DataFrame) -> pd.DataFrame:
    text_cols = ["ts_utc", "run_id"]
    for c in text_cols:
        if c in out.columns:
            out[c] = out[c].astype("string").fillna("")
    if "count" in out.columns:
        out["count"] = pd.to_numeric(
            out["count"], errors="coerce").astype("Int64")
    if "max_calls" in out.columns:
        out["max_calls"] = pd.to_numeric(
            out["max_calls"], errors="coerce").astype("Int64")
    return out


def _normalize_calls_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    ts_col = _first_present(df.columns, "ts_utc", "ts",
                            "timestamp", "time_utc", "time")
    run_col = _first_present(df.columns, "run_id", "run", "runid", "rid")
    phase_col = _first_present(df.columns, "phase", "step", "stage")
    topic_col = _first_present(
        df.columns, "topic_mid", "topic", "keyword", "term")
    tf_col = _first_present(df.columns, "timeframe",
                            "window", "period", "range")
    geo_col = _first_present(df.columns, "geo", "country", "region")
    att_col = _first_present(df.columns, "attempt",
                             "try", "attempt_no", "attempt_n", "tentative")
    status_col = _first_present(df.columns, "status", "state", "result")
    err_col = _first_present(df.columns, "error", "err",
                             "message", "detail", "exception")

    out = pd.DataFrame()
    out["ts_utc"] = _normalize_ts_to_utc_str(df[ts_col]) if ts_col else ""
    out["run_id"] = df[run_col] if run_col else ""
    out["phase"] = df[phase_col] if phase_col else ""
    out["topic_mid"] = df[topic_col] if topic_col else ""
    out["timeframe"] = df[tf_col] if tf_col else ""
    out["geo"] = df[geo_col] if geo_col else ""
    out["attempt"] = df[att_col] if att_col else ""
    out["status"] = df[status_col]if status_col else ""
    out["error"] = df[err_col] if err_col else ""

    # Compléter/ordonner
    for col in EXPECTED_CALLS_COLS:
        if col not in out.columns:
            out[col] = ""
    out = out[EXPECTED_CALLS_COLS]

    return _coerce_calls_types(out)


def _normalize_meter_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    ts_col = _first_present(df.columns, "ts_utc", "ts",
                            "timestamp", "time_utc", "time")
    run_col = _first_present(df.columns, "run_id", "run", "runid", "rid")
    cnt_col = _first_present(df.columns, "count", "calls", "n", "call_count")
    max_col = _first_present(df.columns, "max_calls", "max", "budget", "limit")

    out = pd.DataFrame()
    out["ts_utc"] = _normalize_ts_to_utc_str(df[ts_col]) if ts_col else ""
    out["run_id"] = df[run_col] if run_col else ""
    out["count"] = df[cnt_col] if cnt_col else ""
    out["max_calls"] = df[max_col] if max_col else ""

    for col in EXPECTED_METER_COLS:
        if col not in out.columns:
            out[col] = ""
    out = out[EXPECTED_METER_COLS]

    return _coerce_meter_types(out)


def build_calls_and_meter():
    outdir = _outdir()
    logs = outdir / "logs"
    processed = outdir / "processed"
    _mk(processed)

    # ---- calls_all.csv ----
    call_files = sorted(list(logs.glob("calls__*.csv")) +
                        list(logs.glob("call__*.csv")) + list(logs.glob("calls*.csv")))
    frames = []
    for f in call_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            frames.append(_normalize_calls_df(df))
        except Exception as e:
            print(f"[WARN] Lecture {f.name}: {e}")
    if frames:
        calls_all = pd.concat(frames, ignore_index=True)
        calls_all = calls_all.drop_duplicates(
            subset=EXPECTED_CALLS_COLS, keep="last")
        if "ts_utc" in calls_all.columns:
            calls_all["_order_ts"] = pd.to_datetime(
                calls_all["ts_utc"], errors="coerce", utc=True)
            calls_all = calls_all.sort_values(
                "_order_ts", na_position="last").drop(columns="_order_ts")
        out_calls = processed / "calls_all.csv"
        calls_all.to_csv(out_calls, index=False, encoding="utf-8")
        print(f"[OK] Écrit: {out_calls} ({len(calls_all)} lignes)")
    else:
        print("[INFO] Aucun log d'appels trouvé → pas de calls_all.csv.")

    # ---- meter.csv ----
    meter_files = sorted(list(logs.glob("meter*.csv")))
    mframes = []
    for f in meter_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            mframes.append(_normalize_meter_df(df))
        except Exception as e:
            print(f"[WARN] Lecture {f.name}: {e}")
    if mframes:
        meter = pd.concat(mframes, ignore_index=True)
        meter = meter.drop_duplicates(subset=EXPECTED_METER_COLS, keep="last")
        if "ts_utc" in meter.columns:
            meter["_order_ts"] = pd.to_datetime(
                meter["ts_utc"], errors="coerce", utc=True)
            meter = meter.sort_values(
                "_order_ts", na_position="last").drop(columns="_order_ts")
        out_meter = processed / "meter.csv"
        meter.to_csv(out_meter, index=False, encoding="utf-8")
        print(f"[OK] Écrit: {out_meter} ({len(meter)} lignes)")
    else:
        print("[INFO] Aucun meter*.csv trouvé → pas de meter.csv.")


if __name__ == "__main__":
    build_calls_and_meter()
