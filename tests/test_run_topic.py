# Vérifie qu’un fichier CSV est créé
logdir = outdir / "logs"
files = list(logdir.glob("calls__*.csv"))
assert files, "Aucun fichier CSV généré dans data/logs/"

# Vérifie que le fichier contient bien les colonnes attendues
df = pd.read_csv(files[0])
expected_cols = ["ts_utc", "run_id", "phase", "topic_mid",
                 "timeframe", "geo", "attempt", "status", "error"]
for col in expected_cols:
    assert col in df.columns, f"Colonne manquante: {col}"
