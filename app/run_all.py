# app/run_all.py
"""
Orchestration locale/CI :
1. Choisit le prochain topic (app.next_topic)
2. Synchronise _current_topic.txt vers OUTDIR/config
3. Lance la collecte (app.run_topic)
4. Construit les fichiers de logs (app.aggregate_calls_meter)

Sorties attendues dans data/processed :
- topics_all.csv  (les données Google Trends)
- calls_all.csv   (les logs d’appels)
- meter.csv       (le compteur d’appels)
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path


def run_step(description: str, cmd: list[str]) -> None:
    print(f"\n== {description} ==")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    repo = Path(__file__).resolve().parents[1]

    # OUTDIR : utilisé en CI (ex: data-branch/data) ou local (fallback repo/data)
    outdir = Path(os.getenv("OUTDIR", repo / "data"))
    (outdir / "config").mkdir(parents=True, exist_ok=True)

    # Étape 1 : Sélection du prochain topic
    run_step("Sélection du prochain topic", [
             sys.executable, "-m", "app.next_topic"])

    # Étape 2 : Synchronisation du fichier courant vers OUTDIR/config
    # Cas standard actuel : next_topic écrit dans repo/data/config/_current_topic.txt
    src_primary = repo / "data" / "config" / "_current_topic.txt"
    # Cas futur (si next_topic écrit déjà dans OUTDIR) : on retombe sur le même fichier
    src_fallback = outdir / "config" / "_current_topic.txt"

    if src_primary.exists():
        src = src_primary
    elif src_fallback.exists():
        src = src_fallback
    else:
        raise FileNotFoundError(
            f"Impossible de trouver _current_topic.txt ni dans {src_primary} ni dans {src_fallback}."
        )

    dst = outdir / "config" / "_current_topic.txt"
    shutil.copy2(src, dst)
    print(f"[SYNC] Copié {src} -> {dst}")

    # Étape 3 : Collecte avec le fichier synchronisé
    run_step(
        "Collecte (run_topic)",
        [sys.executable, "-m", "app.run_topic", "--topics-file", str(dst)],
    )

    # Étape 4 : Agrégation des logs
    run_step("Agrégation des logs", [
             sys.executable, "-m", "app.aggregate_calls_meter"])

    print("\nPipeline terminé.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"[ERREUR] Commande échouée ({e.returncode})", file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        sys.exit(1)
