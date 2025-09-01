# GT Collector (Google Trends → CSV)

Pipeline de collecte des indices Google Trends (mots-clés cardiologie) écrivant dans `data/trends.csv`, avec monitoring minimal dans `data/monitoring_runs.csv`.

## 🚀 Lancer en local (Docker)
```bash
cp .env.example .env
docker compose build
docker compose up --abort-on-container-exit
# test schedule
