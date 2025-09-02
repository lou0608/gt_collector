# app/tools/make_fixture_files.py
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import pytz
import os
from app.normalize import normalize_daily, normalize_hourly

BASEDIR = Path(os.getenv("OUTDIR", "/data"))
DAILYDIR = BASEDIR / "raw" / "daily"
HOURLYDIR = BASEDIR / "raw" / "hourly"
for d in (DAILYDIR, HOURLYDIR):
    d.mkdir(parents=True, exist_ok=True)


def make_daily_fixture(topic_mid: str, topic_label: str, geo: str = "FR"):
    dates = pd.date_range("2024-06-01", periods=10,
                          freq="D", tz="UTC").tz_convert("UTC")
    df = pd.DataFrame(
        {"value": [10, 12, 9, 14, 13, 8, 11, 15, 7, 10]}, index=dates)
    df.index.name = "date"
    df_norm = normalize_daily(df, topic_mid, topic_label, geo, "2024")
    run_date = datetime.now(pytz.timezone("Europe/Paris")).strftime("%Y%m%d")
    out = DAILYDIR / f"daily_2024__{topic_label}__{run_date}.csv"
    df_norm.to_csv(out, index=False, encoding="utf-8")
    print(f"[FIXTURE] daily → {out} ({len(df_norm)} lignes)")


def make_hourly_fixture(topic_mid: str, topic_label: str, geo: str = "FR"):
    paris = pytz.timezone("Europe/Paris")
    yesterday = (datetime.now(paris).date() - timedelta(days=1))
    start_paris = paris.localize(
        datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0))
    idx_paris = pd.date_range(start_paris, periods=24, freq="H", tz=paris)
    idx_utc = idx_paris.tz_convert("UTC")  # pytrends renverrait un index UTC
    df = pd.DataFrame({"value": [max(0, 5 + (h % 6)*2)
                      for h in range(24)]}, index=idx_utc)
    df.index.name = "date"
    df_norm = normalize_hourly(df, topic_mid, topic_label, geo, "now 7-d")
    run_date = datetime.now(paris).strftime("%Y%m%d")
    out = HOURLYDIR / f"hourly_7d__{topic_label}__{run_date}.csv"
    df_norm.to_csv(out, index=False, encoding="utf-8")
    print(f"[FIXTURE] hourly → {out} ({len(df_norm)} lignes)")


if __name__ == "__main__":
    make_daily_fixture(topic_mid="/m/01l2m3",
                       topic_label="insuffisance_cardiaque", geo="FR")
    make_hourly_fixture(topic_mid="/m/01l2m3",
                        topic_label="insuffisance_cardiaque", geo="FR")
