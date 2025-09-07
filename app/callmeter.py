from __future__ import annotations

import os
import csv
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

# --- Répertoires & fichiers de log ---
if os.getenv("OUTDIR"):
    BASEDIR = Path(os.getenv("OUTDIR"))
else:
    BASEDIR = Path("/data")  # par défaut : /data dans Docker / Actions

LOGDIR = BASEDIR / "logs"
CONFIGDIR = BASEDIR / "config"
PROCESSED_DIR = BASEDIR / "processed"

for d in (LOGDIR, CONFIGDIR, PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)

# 1) Journal détaillé de chaque appel pytrends
CALLS_ALL_PATH = LOGDIR / "calls_all.csv"
CALLS_DAILY_PATH = LOGDIR / \
    f"calls__{datetime.utcnow().strftime('%Y%m%d')}.csv"

# 2) Jauge/budget des appels
METER_PATH = LOGDIR / "meter.csv"  # <--- utilisé par run_topic.py

CALLS_HEADERS = [
    "ts_utc",       # 2025-09-01T08:12:34Z
    "run_id",       # identifiant du run (RUN_ID)
    "phase",        # daily, hourly, ...
    "topic_mid",    # mot-clé
    "timeframe",    # now 7-d, today 5-y, ...
    "geo",          # FR, "", ...
    "attempt",      # tentative n
    "status",       # ok | 429 | error
    "error",        # message d'erreur éventuel
]

METER_HEADERS = [
    "ts_utc",       # 2025-09-01T08:12:34Z
    "run_id",       # identifiant du run
    "count",        # nombre de hits effectués
    "max_calls",    # plafond
]


def _ts_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_file_with_header(path: Path, headers: list[str]) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


# S’assurer que les fichiers existent avec leurs en-têtes
_ensure_file_with_header(CALLS_ALL_PATH, CALLS_HEADERS)
_ensure_file_with_header(CALLS_DAILY_PATH, CALLS_HEADERS)
_ensure_file_with_header(METER_PATH, METER_HEADERS)


@dataclass
class CallBudget:
    """Compteur d’appels pour éviter les 429."""
    max_calls: int
    run_id: str | None = None
    count: int = 0

    def hit(self) -> None:
        """Déclare un appel à venir. Incrémente le compteur et vérifie le plafond."""
        self.count += 1
        if self.count > self.max_calls:
            # On logge le dépassement avant d’échouer
            self._write_meter()
            raise RuntimeError(
                f"Budget d'appels dépassé: {self.count}/{self.max_calls}")
        self._write_meter()

    def _write_meter(self) -> None:
        with METER_PATH.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([_ts_utc(), (self.run_id or ""),
                            self.count, self.max_calls])


def log_call(run_id: str,
             phase: str,
             topic_mid: str,
             timeframe: str,
             geo: str,
             attempt: int,
             status: str,
             error: str = "",
             path: Path | None = None) -> None:
    """Écrit une ligne de log pour un appel pytrends (succès / 429 / erreur)."""

    error = (error or "").replace("\n", " ").replace("\r", " ")[:500]
    row = [
        _ts_utc(),
        run_id,
        phase,
        topic_mid,
        timeframe,
        geo,
        attempt,
        status,
        error,
    ]

    # écrit toujours dans calls_all.csv et calls__YYYYMMDD.csv
    for target in [CALLS_ALL_PATH, CALLS_DAILY_PATH]:
        file_exists = target.exists()
        with target.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(CALLS_HEADERS)
            writer.writerow(row)

    # Si l'appel est explicitement redirigé vers un autre fichier
    if path and path not in (CALLS_ALL_PATH, CALLS_DAILY_PATH):
        file_exists = path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(CALLS_HEADERS)
            writer.writerow(row)
