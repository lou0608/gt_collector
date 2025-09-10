from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import pandas as pd
from pathlib import Path

FILES = [
    Path("/opt/airflow/dags/data/raw/topic=infarctus_du_myocarde.csv"),
    Path("/opt/airflow/dags/data/raw/topic=insuffisance_cardiaque.csv"),
]
OUTPUT = Path("/opt/airflow/dags/data/processed/trends_consolidated.csv")


def check_files_exist():
    for f in FILES:
        if not f.exists():
            raise FileNotFoundError(f"{f} introuvable")
    print("✅ Tous les fichiers sources existent")


def consolidate_csvs():
    dfs = [pd.read_csv(f) for f in FILES]
    df = pd.concat(dfs)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)
    print(f"✅ Consolidation terminée : {OUTPUT}")


with DAG(
    "gt_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:
    t1 = PythonOperator(task_id="check_files_exist",
                        python_callable=check_files_exist)
    t2 = PythonOperator(task_id="consolidate_csvs",
                        python_callable=consolidate_csvs)
    t1 >> t2
