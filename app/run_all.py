# app/run_all.py
"""
Orchestration locale/CI :
1) SYNC topics.txt -> OUTDIR/config
2) Choisit le prochain topic (app.next_topic)
3) Lit le topic courant depuis OUTDIR/config/_current_topic.txt
4) Lance la collecte (app.run_topic)
5) Agrège les logs (app.aggregate_calls_meter)

Sorties attendues dans OUTDIR/processed :
- topics_all.csv  (données Google Trends)
- calls_all.csv   (logs d’appels)
- meter.csv       (compteur d’appels)
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


def safe_copy(src: Path, dst: Path, label: str) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"[SYNC {label}] Copié {src} -> {dst}")
    else:
        print(f"[SYNC {label}] Source absente : {src}")


def read_str(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    outdir = Path(os.getenv("OUTDIR", repo / "data"))
    (outdir / "config").mkdir(parents=True, exist_ok=True)

    # 1) Synchroniser topics.txt (source = repo) vers OUTDIR
    topics_src = repo / "data" / "config" / "topics.txt"
    topics_dst = outdir / "config" / "topics.txt"
    safe_copy(topics_src, topics_dst, "TOPICS")

    # 2) Sélection du prochain topic (écrit OUTDIR/_current_topic.txt)
    run_step("Sélection du prochain topic", [
             sys.executable, "-m", "app.next_topic"])

    # 3) Lire le topic courant depuis OUTDIR
    current_file = outdir / "config" / "_current_topic.txt"
    if not current_file.exists():
        raise FileNotFoundError(
            f"_current_topic.txt introuvable dans {current_file} (next_topic a-t-il tourné ?)")
    print(
        f"[CHECK] Topic OUTDIR/_current_topic.txt = {read_str(current_file)}")

    # 4) Collecte (forcée à utiliser le fichier OUTDIR)
    run_step(
        "Collecte (run_topic)",
        [sys.executable, "-m", "app.run_topic",
            "--topics-file", str(current_file)],
    )

    # 5) Agrégation des logs
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
