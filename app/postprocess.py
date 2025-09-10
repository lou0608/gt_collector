from __future__ import annotations
import pandas as pd
from pathlib import Path
from datetime import datetime

from app.paths import PROCESSED_DIR, LOGDIR, ensure_dirs


def main():
    # Créer les dossiers si besoin
    ensure_dirs()

    # Date du jour pour nommer le fichier
    today = datetime.today().strftime("%Y%m%d")

    # Les fichiers générés par run_topic
    daily_files = list(LOGDIR.glob("calls__*.csv"))

    if not daily_files:
        print("[WARN] Aucun fichier brut trouvé dans data/logs/")
        return

    # Charger et concaténer les CSV
    frames = []
    for f in daily_files:
        try:
            df = pd.read_csv(f)
            frames.append(df)
        except Exception as e:
            print(f"[WARN] Impossible de lire {f}: {e}")

    if not frames:
        print("[WARN] Aucun CSV valide à concaténer.")
        return

    df_all = pd.concat(frames, ignore_index=True)

    # Sauvegarder le fichier du jour
    daily_out = PROCESSED_DIR / f"topics__{today}.csv"
    df_all.to_csv(daily_out, index=False, encoding="utf-8")
    print(f"[OK] Fichier journalier écrit: {daily_out}")

    # Mettre à jour le topics_all.csv
    all_out = PROCESSED_DIR / "topics_all.csv"
    if all_out.exists():
        old = pd.read_csv(all_out)
        df_all = pd.concat([old, df_all], ignore_index=True)
    df_all.to_csv(all_out, index=False, encoding="utf-8")
    print(f"[OK] Fichier global mis à jour: {all_out}")


if __name__ == "__main__":
    main()
