# app/run_all.py
"""
Orchestration locale :
1. Choisit le prochain topic (app.next_topic)
2. Lance la collecte (app.run_topic)
3. Construit les fichiers de logs (app.aggregate_calls_meter)

Sorties attendues dans data/processed :
- topics_all.csv  (les données Google Trends)
- calls_all.csv   (les logs d’appels)
- meter.csv       (le compteur d’appels)
"""

import sys
import subprocess
from pathlib import Path


def run_step(description: str, cmd: list[str]) -> None:
    print(f"\n== {description} ==")
    print(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERREUR] {description} a échoué ({e.returncode})")
        sys.exit(e.returncode)


def main():
    repo = Path(__file__).resolve().parents[1]
    outdir = repo / "data"

    # Étape 1 : next_topic
    run_step("Sélection du prochain topic", [
             sys.executable, "-m", "app.next_topic"])

    # Étape 2 : run_topic
    topics_file = outdir / "config" / "_current_topic.txt"
    run_step("Collecte (run_topic)", [
             sys.executable, "-m", "app.run_topic", "--topics-file", str(topics_file)])

    # Étape 3 : logs (aggregate_calls_meter)
    run_step("Agrégation des logs", [
             sys.executable, "-m", "app.aggregate_calls_meter"])

    print("\n Pipeline local terminé.")


if __name__ == "__main__":
    main()
