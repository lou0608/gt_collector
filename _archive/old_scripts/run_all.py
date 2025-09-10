#!/usr/bin/env python3
import subprocess
import sys
import shlex


def run(cmd: str, soft=False):
    print(f"\n$ {cmd}")
    r = subprocess.run(shlex.split(cmd))
    if r.returncode != 0:
        if soft:
            print(
                f"[WARN] commande échouée (code={r.returncode}) mais on continue.")
        else:
            sys.exit(r.returncode)


def main():
    # 1. Collecte
    run("python -u -m app.run_topic")

    # 2. Agrégation des logs
    run("python -u -m app.tools.aggregate_logs", soft=True)

    # 3. Healthcheck
    run("python -u -m app.tools.healthcheck", soft=True)

    print("\n[OK] run_all terminé.")


if __name__ == "__main__":
    main()
