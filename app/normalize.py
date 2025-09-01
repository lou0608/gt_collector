# app/normalize.py
from datetime import datetime
import pandas as pd
import pytz


def normalize_daily(df: pd.DataFrame, topic_mid, topic_label, geo, window):
    df = df.copy()
    if df.index.name is None or str(df.index.name).lower() != "date":
        df.index.name = "date"
    df = df.reset_index()

    # Identifier la colonne valeur (celle qui n'est pas date/isPartial)
    valcol = [c for c in df.columns if c not in ("date", "isPartial")]
    if len(valcol) == 1:
        df.rename(columns={valcol[0]: "value"}, inplace=True)

    if "isPartial" in df.columns:
        df.drop(columns=["isPartial"], inplace=True)

    df["date"] = pd.to_datetime(df["date"], utc=True).dt.date.astype(str)
    df["value"] = df["value"].astype(int)
    df["topic_mid"] = topic_mid
    df["topic_label"] = topic_label
    df["geo"] = geo or ""
    df["window"] = str(window)
    df["created_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    return df[["date", "value", "topic_mid", "topic_label", "geo", "window", "created_at"]]


def normalize_hourly(df: pd.DataFrame, topic_mid, topic_label, geo, window):
    df = df.copy()
    df.index.name = "datetime_utc"
    df["value"] = df.iloc[:, 0].astype(int)

    # Passage en fuseau Europe/Paris
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df["datetime_paris"] = df.index.tz_convert("Europe/Paris")
    df["date"] = df["datetime_paris"].dt.strftime("%Y-%m-%d")
    df["hour"] = df["datetime_paris"].dt.hour

    df["topic_mid"] = topic_mid
    df["topic_label"] = topic_label
    df["geo"] = geo or ""
    df["window"] = window
    df["created_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    return df[["datetime_paris", "date", "hour", "value", "topic_mid", "topic_label", "geo", "window", "created_at"]]
