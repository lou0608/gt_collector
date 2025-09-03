# app/tools/run_daily_only.py
import os
import argparse
import pytz
from datetime import datetime
from pathlib import Path

# Dossiers portables (CI → ./data, local/Docker → /data, ou OUTDIR si défini)
if os.getenv("GITHUB_ACTIONS") == "true":
    BASEDIR = Path("data")
else:
    BASEDIR = Path(os.getenv("OUTDIR", "/data"))

RAWDIR = BASEDIR / "raw"
DAILYDIR = RAWDIR / "daily"
for d in (RAWDIR, DAILYDIR):
    d.mkdir(parents=True, exist_ok=True)

# On réutilise les fonctions existantes de run_topic
from app.run_topic import _write_daily_2024, _slugify  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Daily-only Google Trends (2024)")
    ap.add_argument("--topic-mid", required=True,
                    help="ID topic (MID), ex: /m/01wgr")
    ap.add_argument("--topic-label", required=True,
                    help="Label lisible, ex: hypertension")
    args = ap.parse_args()

    topic_mid = args.topic_mid
    topic_label = args.topic_label
    topic_slug = _slugify(topic_label)

    # Datestamp Europe/Paris (même convention que run_topic)
    run_date = datetime.now(pytz.timezone("Europe/Paris")).strftime("%Y%m%d")

    # Daily 2024 uniquement
    _write_daily_2024(topic_mid, topic_label, topic_slug, run_date)


if __name__ == "__main__":
    main()
