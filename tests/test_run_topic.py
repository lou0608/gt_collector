import subprocess
import os
from pathlib import Path
import pandas as pd


def test_run_topic_creates_log(tmp_path):
    """
    Vérifie que run_topic.py appelle log_call et écrit bien un fichier CSV dans data/logs/.
    """

    # On redéfinit OUTDIR vers un répertoire temporaire
    outdir = tmp_path
    env = os.environ.copy()
    env["OUTDIR"] = str(outdir)

    # Lance run_topic.py avec un topic simple
    result = subprocess.run(
        ["python", "-m", "app.run_topic", "--topics", "test_topic"],
        env=env,
        capture_output=True,
        text=True,
    )

    # Vérifie que le script s’est exécuté correctement
    assert result.returncode == 0, f"Erreur run_topic.py : {result.stderr}"

    # Vérifie qu’un fichier CSV est créé dans data/logs/
    logdir = outdir / "logs"
    files = list(logdir.glob("calls__*.csv"))
    assert files, "Aucun fichier CSV généré dans data/logs/"

    # Vérifie que le fichier contient bien les colonnes attendues
    df = pd.read_csv(files[0])
    expected_cols = [
        "ts_utc", "run_id", "phase", "topic_mid",
        "timeframe", "geo", "attempt", "status", "error"
    ]
    for col in expected_cols:
        assert col in df.columns, f"Colonne manquante: {col}"
