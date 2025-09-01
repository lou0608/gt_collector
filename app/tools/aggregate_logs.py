# app/tools/aggregate_logs.py
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd
from datetime import datetime

DATA = Path("/data")


def _read_csv_safe(p: Path) -> pd.DataFrame:
    if not p.exists():
        print(f"[ERR] Fichier introuvable: {p}", file=sys.stderr)
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception as e:
        print(f"[ERR] Lecture CSV échouée: {p} → {e}", file=sys.stderr)
        return pd.DataFrame()


def _first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _parse_day_col(df: pd.DataFrame) -> pd.Series | None:
    # Cherche une colonne timestamp/temps et renvoie la date (YYYY-MM-DD)
    ts_col = _first_existing_col(
        df, ["timestamp", "ts", "time", "datetime", "date"])
    if not ts_col:
        return None
    try:
        ts = pd.to_datetime(df[ts_col], errors="coerce",
                            utc=True).dt.tz_convert("Europe/Paris")
    except Exception:
        ts = pd.to_datetime(df[ts_col], errors="coerce")
    return ts.dt.date


def _status_bucket(s: pd.Series) -> pd.Series:
    # Mappe un statut HTTP numérique en catégories
    s_num = pd.to_numeric(s, errors="coerce")
    bucket = pd.Series(["other"] * len(s), index=s.index, dtype="object")
    bucket[(s_num >= 200) & (s_num <= 299)] = "ok_2xx"
    bucket[(s_num >= 400) & (s_num <= 499)] = "err_4xx"
    bucket[(s_num >= 500) & (s_num <= 599)] = "err_5xx"
    return bucket


def summarize_calls(calls_csv: Path) -> Path | None:
    df = _read_csv_safe(calls_csv)
    if df.empty:
        print("[WARN] calls.csv vide ou illisible → pas de résumé.")
        return None

    day = _parse_day_col(df)
    if day is None:
        # fallback: tout dans une seule 'day'
        day = pd.Series([datetime.utcnow().date()] * len(df))

    status_col = _first_existing_col(
        df, ["status", "http_status", "code", "status_code"])
    if status_col is None:
        status_bucket = pd.Series(["other"] * len(df), dtype="object")
    else:
        status_bucket = _status_bucket(df[status_col])

    topic_col = _first_existing_col(df, ["topic_mid", "mid", "topic"])
    endpoint_col = _first_existing_col(df, ["endpoint", "fn", "route", "path"])

    grp = pd.DataFrame({
        "day": day,
        "bucket": status_bucket
    })

    # Compte par jour & bucket
    by_day_bucket = (grp
                     .value_counts(["day", "bucket"])
                     .rename("count")
                     .reset_index())

    # Pivot pour colonnes ok_2xx/err_4xx/err_5xx/other
    pivot = by_day_bucket.pivot(
        index="day", columns="bucket", values="count").fillna(0).reset_index()
    for col in ["ok_2xx", "err_4xx", "err_5xx", "other"]:
        if col not in pivot.columns:
            pivot[col] = 0

    # Totaux et métriques utiles
    total_calls = pivot[["ok_2xx", "err_4xx", "err_5xx", "other"]].sum(axis=1)
    pivot.insert(1, "total_calls", total_calls)

    # Uniques si colonnes présentes
    uniq_topics = (df.groupby(day)[topic_col].nunique() if topic_col else pd.Series(
        0, index=pivot["day"])).reindex(pivot["day"]).fillna(0).astype(int)
    uniq_endpoints = (df.groupby(day)[endpoint_col].nunique() if endpoint_col else pd.Series(
        0, index=pivot["day"])).reindex(pivot["day"]).fillna(0).astype(int)

    pivot["uniq_topics"] = uniq_topics.values
    pivot["uniq_endpoints"] = uniq_endpoints.values

    out = DATA / f"calls_summary__{datetime.utcnow().strftime('%Y%m%d')}.csv"
    pivot.sort_values("day").to_csv(out, index=False)
    print(f"[OK] Résumé appels → {out} ({len(pivot)} lignes)")
    return out


def summarize_meter(meter_csv: Path) -> Path | None:
    df = _read_csv_safe(meter_csv)
    if df.empty:
        print("[WARN] meter.csv vide ou illisible → pas de résumé.")
        return None

    day = _parse_day_col(df)
    if day is None:
        day = pd.Series([datetime.utcnow().date()] * len(df))

    # Heuristiques : si la colonne 'event' existe (cooldown/backoff/etc.)
    event_col = _first_existing_col(df, ["event", "type", "evt"])
    backoff_col = _first_existing_col(
        df, ["backoff_s", "backoff_sec", "sleep_s"])
    quota_col = _first_existing_col(df, ["quota", "quota_left", "quota_used"])

    # Compte d'événements par jour & type
    if event_col:
        by_day_event = (pd.DataFrame({"day": day, "event": df[event_col]})
                        .value_counts(["day", "event"])
                        .rename("count")
                        .reset_index())
        pivot_evt = by_day_event.pivot(
            index="day", columns="event", values="count").fillna(0).reset_index()
    else:
        pivot_evt = pd.DataFrame({"day": day}).value_counts(
            "day").rename("events").reset_index()

    # Agrégats complémentaires
    agg = df.copy()
    agg["day"] = day
    sums = agg.groupby("day").agg(
        total_rows=("day", "size"),
        total_backoff_s=(backoff_col, "sum") if backoff_col else (
            "day", "size"),
    ).reset_index()
    if backoff_col is None:
        sums["total_backoff_s"] = 0

    # Merge
    summary = pd.merge(pivot_evt, sums, on="day", how="outer").fillna(0)

    # Optionnel: min/max quota si dispo
    if quota_col:
        q = agg.groupby("day")[quota_col].agg(["min", "max"]).reset_index()
        q.columns = ["day", "quota_min", "quota_max"]
        summary = pd.merge(summary, q, on="day", how="left").fillna(0)

    out = DATA / f"meter_summary__{datetime.utcnow().strftime('%Y%m%d')}.csv"
    summary.sort_values("day").to_csv(out, index=False)
    print(f"[OK] Résumé meter → {out} ({len(summary)} lignes)")
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Agrégateur de logs pour Power BI")
    ap.add_argument(
        "--calls",
        type=Path,
        default=DATA / "logs" / "calls__20250901.csv",
        help="Chemin CSV des appels (ex: /data/logs/calls__YYYYMMDD.csv)",
    )
    ap.add_argument(
        "--meter",
        type=Path,
        default=DATA / "meter.csv",
        help="Chemin CSV meter (ex: /data/meter.csv | /data/gt_meter.csv | /data/gt_meters.csv)",
    )
    args = ap.parse_args()

    # Résumé calls
    calls_out = summarize_calls(args.calls)

    # Auto-détection meter si le chemin fourni n'existe pas
    if not args.meter.exists():
        for cand in ["gt_meter.csv", "gt_meters.csv", "meter.csv"]:
            p = DATA / cand
            if p.exists():
                print(f"[INFO] meter introuvable → utilisation de {p}")
                args.meter = p
                break

    meter_out = summarize_meter(args.meter)

    ok_any = (calls_out is not None) or (meter_out is not None)
    if not ok_any:
        sys.exit(1)


if __name__ == "__main__":
    main()
