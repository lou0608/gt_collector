#!/usr/bin/env python3
import os
import sys
import subprocess
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CWD = str(ROOT)
DC = os.environ.get("DOCKER_COMPOSE", "docker compose")


def run(cmd: str, cwd=CWD, env=None):
    print(f"\n$ {cmd}")
    r = subprocess.run(shlex.split(cmd), cwd=cwd, env=env)
    if r.returncode != 0:
        sys.exit(r.returncode)


def run_soft(cmd: str, cwd=CWD, env=None):
    """Exécute une commande mais n'arrête pas le script si elle échoue."""
    print(f"\n$ {cmd}")
    r = subprocess.run(shlex.split(cmd), cwd=cwd, env=env)
    if r.returncode != 0:
        print(
            f"[WARN] commande échouée (code={r.returncode}) mais on continue.")


def getenv_bool(name: str, default=False):
    v = (os.environ.get(name) or "").strip().lower()
    if v in {"1", "true", "yes", "y"}:
        return True
    if v in {"0", "false", "no", "n"}:
        return False
    return default


def main():
    # --- Paramètres via variables d'env ---
    MID = os.environ.get("RUN_TOPIC_MID") or ""
    LABEL = os.environ.get("RUN_TOPIC_LABEL") or "topic"
    RUN_DAILY = getenv_bool("RUN_DAILY", True)
    RUN_HOURLY = getenv_bool("RUN_HOURLY", False)
    HOURLY_MODE = os.environ.get("HOURLY_MODE") or "bootstrap"
    AGG_LOGS = getenv_bool("AGG_LOGS", True)
    DO_HEALTH = getenv_bool("DO_HEALTHCHECK", True)

    OFFLINE = getenv_bool("GT_OFFLINE_FIXTURE", False)
    offline_flag = "-e GT_OFFLINE_FIXTURE=1" if OFFLINE else ""

    (ROOT/"data").mkdir(exist_ok=True)
    (ROOT/"logs").mkdir(exist_ok=True)

    # --- Build idempotent ---
    run(f"{DC} pull")
    run(f"{DC} build --pull")

    # --- Collecte ---
    if MID:
        if RUN_DAILY:
            cmd = (
                f'{DC} run --rm -e PYTHONUNBUFFERED=1 {offline_flag} '
                f'gt-collector python -u -m app.run_topic '
                f'--topic-mid "{MID}" --topic-label "{LABEL}"'
            )
            run(cmd)

        if RUN_HOURLY:
            cmd = (
                f'{DC} run --rm -e PYTHONUNBUFFERED=1 {offline_flag} '
                f'gt-collector python -u -m app.run_topic '
                f'--topic-mid "{MID}" --topic-label "{LABEL}" '
                f'--only-hourly --hourly-mode {HOURLY_MODE}'
            )
            run(cmd)
    else:
        print("[WARN] RUN_TOPIC_MID non défini → collecte sautée.")

    # --- Agrégation des logs ---
    if AGG_LOGS:
        cmd = (
            f'{DC} run --rm -e PYTHONUNBUFFERED=1 -e PYTHONPATH=/app '
            f'gt-collector python -u -c "import app.tools.aggregate_logs as m; m.main()"'
        )
        run(cmd)

    # --- Healthcheck (soft-fail) ---
    if DO_HEALTH:
        hc_max_err = os.environ.get("HC_MAX_ERR_RATE", "1.00")  # tolérant
        hc_req_today = os.environ.get("HC_REQUIRE_TODAY", "1")
        cmd = (
            f'{DC} run --rm -e PYTHONUNBUFFERED=1 -e PYTHONPATH=/app '
            f'-e HC_MAX_ERR_RATE={hc_max_err} -e HC_REQUIRE_TODAY={hc_req_today} '
            f'gt-collector python -u -m app.tools.healthcheck'
        )
        run_soft(cmd)

    print("\n[OK] run_all terminé.")


if __name__ == "__main__":
    main()
