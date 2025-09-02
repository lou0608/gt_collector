# app/callmeter.py
from __future__ import annotations

import os
import csv
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

# --- Répertoires & fichiers de log ---
# On choisit le répertoire en fonction de l'environnement :
# - En GitHub Actions : ./data/logs (dans le repo, artefacts faciles à uploader)
# - Sinon (Docker/local) : /data/logs (cohérent avec les montages Docker)

if os.getenv("GITHUB_ACTIONS") == "true":
    BASEDIR = Path("data")
else:
    BASEDIR = Path(os.getenv("OUTDIR", "/data"))

LOGDIR = BASEDIR / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

# 1) Journal détaillé de chaque appel pytrends (roté quotidiennement)
CALLS_CSV = LOGDIR / f"calls__{datetime.now().strftime('%Y%m%d')}.csv"

# 2) Jauge/budget des appels (append, simple à grafer)
METER_PATH = LOGDIR / "meter.csv"  # <--- utilisé par run_topic.py pour affichage

CALLS_HEADERS = [
    "ts_utc",       # 2025-09-01T08:12:34Z
    "run_id",       # identifiant du run (RUN_ID)
    "phase",        # daily_2024, hourly_7d_bootstrap, hourly_yesterday, ...
    "topic_mid",    # /m/01l2m3
    "timeframe",    # 2024-01-01 2024-12-31, now 7-d, ...
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


# S’assurer que les fichiers (du jour) existent avec leurs en-têtes
_ensure_file_with_header(CALLS_CSV, CALLS_HEADERS)
_ensure_file_with_header(METER_PATH, METER_HEADERS)


@dataclass
class CallBudget:
    """Compteur d’appels pour éviter les 429.
    - max_calls: nombre d’appels autorisés pour ce process
    - count: compteur courant (auto-incrémenté par hit())
    À chaque hit(), on logge un point dans meter.csv pour faciliter le monitoring.
    """
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
             error: str = "") -> None:
    """Écrit une ligne de log pour un appel pytrends (succès / 429 / erreur)."""
    # Sanitize pour éviter de casser la CSV
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
    with CALLS_CSV.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)
