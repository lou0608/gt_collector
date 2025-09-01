# scripts/run_all.ps1
# Lancer depuis la racine du repo (là où se trouve le dossier scripts)

$ErrorActionPreference = "Stop"

# 1) Sanity: vérifier qu'on est à la racine
if (-not (Test-Path -Path ".\scripts\run_all.py")) {
    throw "Lance ce script depuis la racine du repo (où il y a .\scripts\run_all.py)."
}

# 2) Définir la commande docker compose si absente
if (-not $env:DOCKER_COMPOSE) {
    $env:DOCKER_COMPOSE = "docker compose"
}

# 3) Vérifier que Python est accessible
python --version | Out-Null

# 4) Appeler l'orchestrateur Python
python .\scripts\run_all.py
