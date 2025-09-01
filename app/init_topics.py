# app/init_topics.py
from pathlib import Path
import csv
import argparse

DEFAULT_ROWS = [
    {"query": "hypertension", "label": "Hypertension",
        "expected_type": "Medical condition", "enabled": "1"},
    {"query": "insuffisance cardiaque", "label": "Insuffisance cardiaque",
        "expected_type": "Medical condition", "enabled": "1"},
    {"query": "arythmie", "label": "Arythmie",
        "expected_type": "Medical condition", "enabled": "1"},
]


def ensure_dirs(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def write_topics_csv(path: Path, rows):
    ensure_dirs(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["query", "label", "expected_type", "enabled"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Initialise data/meta/topics.csv avec des requêtes par défaut.")
    parser.add_argument(
        "--file", default="/data/meta/topics.csv", help="Chemin du topics.csv")
    parser.add_argument("--reset", action="store_true",
                        help="Écrase le fichier s'il existe")
    args = parser.parse_args()

    out = Path(args.file)
    if out.exists() and not args.reset:
        print(f"[SKIP] {out} existe déjà. Utilise --reset pour le régénérer.")
        return

    write_topics_csv(out, DEFAULT_ROWS)
    print(f"[OK] {out} créé avec {len(DEFAULT_ROWS)} lignes.")


if __name__ == "__main__":
    main()
