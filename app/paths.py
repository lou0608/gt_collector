# app/paths.py
from __future__ import annotations
import os
from pathlib import Path

# Racine du repo (= dossier qui contient "app" et "data")
REPO_ROOT = Path(__file__).resolve().parents[1]

# OUTDIR : absolu ou relatif ; défaut "data" dans le repo
_raw_outdir = os.getenv("OUTDIR")
if _raw_outdir:
    OUTDIR = Path(_raw_outdir).resolve()
else:
    OUTDIR = (REPO_ROOT / "data").resolve()

DATA_DIR = OUTDIR
LOGDIR = DATA_DIR / "logs"
PROCESSED_DIR = DATA_DIR / "processed"
CONFIG_DIR = DATA_DIR / "config"
STATE_DIR = DATA_DIR / "state"


def ensure_dirs() -> dict[str, Path]:
    for d in (LOGDIR, PROCESSED_DIR, CONFIG_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "data": DATA_DIR,
        "logs": LOGDIR,
        "processed": PROCESSED_DIR,
        "config": CONFIG_DIR,
        "state": STATE_DIR,
    }
