import os


def test_files_exist():
    """Vérifie que les fichiers CSV figés Google Trends existent bien"""
    assert os.path.exists(
        "airflow/dags/data/raw/topic=infarctus_du_myocarde.csv"), "❌ Fichier infarctus manquant"
    assert os.path.exists(
        "airflow/dags/data/raw/topic=insuffisance_cardiaque.csv"), "❌ Fichier insuffisance cardiaque manquant"


def test_files_not_empty():
    """Vérifie que les fichiers ne sont pas vides"""
    for f in [
        "airflow/dags/data/raw/topic=infarctus_du_myocarde.csv",
        "airflow/dags/data/raw/topic=insuffisance_cardiaque.csv",
    ]:
        assert os.path.getsize(f) > 0, f"❌ Le fichier {f} est vide"
