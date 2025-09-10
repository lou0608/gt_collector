# app/postprocess.py
# Consolidation locale "propre"
# - topics__YYYYMMDD.csv + topics_all.csv : construits EXCLUSIVEMENT depuis OUTDIR/raw/daily/*.csv
# - call_all.csv (+ calls__YYYYMMDD.csv, meter_all.csv) : construits depuis OUTDIR/logs/*
from __future__ import annotations
import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd


def get_outdir() -> Path:
    return Path(os.getenv("OUTDIR", "data")).resolve()


def _mk(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _parse_date_in_name(p: Path):
    m = re.search(r"(\d{8})", p.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _norm_topic_df(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    # Normalise en format long: date | topic | value | is_partial | source_file
    low = {c.lower(): c for c in df.columns}
    # Cas 1 : déjà (date, topic, value)
    if {"date", "topic", "value"} <= set(k.lower() for k in df.columns):
        out = df.rename(columns=str.lower).copy()
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
        if "is_partial" not in out.columns:
            out["is_partial"] = False
        out["source_file"] = Path(source_file).name
        return out[["date", "topic", "value", "is_partial", "source_file"]]
    # Cas 2 : style PyTrends (topics + isPartial, date en index/colonne)
    if "ispartial" in low or "is_partial" in low:
        df2 = df.copy()
        if not any(c.lower() == "date" for c in df2.columns):
            df2 = df2.reset_index().rename(columns={"index": "date"})
        date_col = "date" if "date" in df2.columns else list(df2.columns)[0]
        topic_cols = [c for c in df2.columns if c.lower() not in (
            "date", "ispartial", "is_partial")]
        long_df = df2.melt(
            id_vars=[date_col], value_vars=topic_cols, var_name="topic", value_name="value")
        long_df = long_df.rename(columns={date_col: "date"})
        if "isPartial" in df2.columns:
            try:
                long_df["is_partial"] = df2["isPartial"].repeat(
                    len(topic_cols)).reset_index(drop=True)
            except:
                long_df["is_partial"] = False
        elif "is_partial" in df2.columns:
            try:
                long_df["is_partial"] = df2["is_partial"].repeat(
                    len(topic_cols)).reset_index(drop=True)
            except:
                long_df["is_partial"] = False
        else:
            long_df["is_partial"] = False
        long_df["date"] = pd.to_datetime(
            long_df["date"], errors="coerce").dt.date
        long_df["source_file"] = Path(source_file).name
        return long_df[["date", "topic", "value", "is_partial", "source_file"]]
    # Cas 3 : fallback (on melt tout sauf la date)
    df3 = df.copy()
    date_candidates = [c for c in df3.columns if c.lower() in (
        "date", "timestamp", "dt")]
    if not date_candidates:
        raise ValueError(f"Impossible d'inférer la date pour {source_file}")
    date_col = date_candidates[0]
    value_cols = [c for c in df3.columns if c !=
                  date_col and c.lower() not in ("ispartial", "is_partial")]
    long_df = df3.melt(
        id_vars=[date_col], value_vars=value_cols, var_name="topic", value_name="value")
    long_df = long_df.rename(columns={date_col: "date"})
    long_df["date"] = pd.to_datetime(long_df["date"], errors="coerce").dt.date
    long_df["is_partial"] = False
    long_df["source_file"] = Path(source_file).name
    return long_df[["date", "topic", "value", "is_partial", "source_file"]]


def build_topics(processed_dir: Path, raw_daily_dir: Path) -> None:
    files = sorted(raw_daily_dir.glob("*.csv"))
    if not files:
        print("[INFO] Aucun fichier dans raw/daily → on ne touche pas topics_all.csv.")
        return
    dated = []
    for f in files:
        d = _parse_date_in_name(f)
        if d is None:
            try:
                tmp = pd.read_csv(f)
                if "date" in tmp.columns:
                    d = pd.to_datetime(
                        tmp["date"], errors="coerce").dt.date.max()
            except:
                d = None
        if d is not None:
            dated.append((f, d))
    if not dated:
        print("[INFO] Fichiers raw/daily présents mais aucune date détectée.")
        return

    latest = max(d for _, d in dated)
    todays = [f for f, d in dated if d == latest]

    parts = []
    for f in todays:
        try:
            df = pd.read_csv(f)
            nf = _norm_topic_df(df, f.as_posix())
            nf = nf[nf["date"] == latest]
            parts.append(nf)
        except Exception as e:
            print(f"[WARN] Normalisation échouée pour {f.name}: {e}")

    if not parts:
        print("[INFO] Pas de données normalisables pour la date du jour.")
        return

    day_df = pd.concat(parts, ignore_index=True)
    day_path = processed_dir / f"topics__{latest.strftime('%Y%m%d')}.csv"
    day_df.to_csv(day_path, index=False, encoding="utf-8")
    print(f"[OK] Fichier journalier écrit: {day_path}")

    all_path = processed_dir / "topics_all.csv"
    if all_path.exists():
        prev = pd.read_csv(all_path)
        merged = pd.concat([prev, day_df], ignore_index=True)
    else:
        merged = day_df.copy()
    merged = merged.sort_values(["date", "topic"]).drop_duplicates(
        subset=["date", "topic"], keep="last")
    merged.to_csv(all_path, index=False, encoding="utf-8")
    print(f"[OK] Fichier global mis à jour: {all_path}")


def build_calls(processed_dir: Path, logs_dir: Path) -> None:
    call_files = sorted(logs_dir.glob("calls__*.csv"))
    if call_files:
        frames = []
        for f in call_files:
            try:
                df = pd.read_csv(f)
                df["source_file"] = f.name
                frames.append(df)
            except Exception as e:
                print(f"[WARN] Lecture log {f.name}: {e}")
        if frames:
            all_calls = pd.concat(frames, ignore_index=True)
            if "ts" in all_calls.columns:
                all_calls["ts"] = pd.to_datetime(
                    all_calls["ts"], errors="coerce")
            out_all = processed_dir / "call_all.csv"
            all_calls.to_csv(out_all, index=False, encoding="utf-8")
            print(f"[OK] Fichier log consolidé: {out_all}")
            if "ts" in all_calls.columns:
                last_date = all_calls["ts"].dt.date.max()
                day_calls = all_calls[all_calls["ts"].dt.date == last_date]
                (processed_dir / f"calls__{last_date.strftime('%Y%m%d')}.csv").write_text(
                    day_calls.to_csv(index=False), encoding="utf-8"
                )
    meter_files = sorted(logs_dir.glob("meter*.csv"))
    if meter_files:
        frames = []
        for f in meter_files:
            try:
                df = pd.read_csv(f)
                df["source_file"] = f.name
                frames.append(df)
            except Exception as e:
                print(f"[WARN] Lecture meter {f.name}: {e}")
        if frames:
            meter_all = pd.concat(frames, ignore_index=True)
            (processed_dir / "meter_all.csv").write_text(
                meter_all.to_csv(index=False), encoding="utf-8")


def main() -> None:
    outdir = get_outdir()
    processed = outdir / "processed"
    raw_daily = outdir / "raw" / "daily"
    logs = outdir / "logs"
    for d in (processed, raw_daily, logs):
        _mk(d)
    # données d'intérêt UNIQUEMENT depuis raw/daily
    build_topics(processed, raw_daily)
    build_calls(processed, logs)        # logs UNIQUEMENT depuis logs/


if __name__ == "__main__":
    main()
