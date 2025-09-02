from pathlib import Path
import csv
import sys
import os

# ====== Config ======
# /data est monté par Docker ; sur GitHub Actions → ./data
if os.getenv("GITHUB_ACTIONS") == "true":
    DATA = Path("data")
else:
    DATA = Path(os.getenv("OUTDIR", "/data"))

# création sécurisée du dossier
DATA.mkdir(parents=True, exist_ok=True)

if len(sys.argv) < 2:
    print("Usage: python -m app.tools.print_first_mid <slug-mot-cle>")
    sys.exit(1)

slug = sys.argv[1]
files = sorted(DATA.glob(f"topics_suggestions__{slug}__*.csv"))
if not files:
    print(f"[ERR] Aucun fichier topics_suggestions__{slug}__*.csv")
    sys.exit(2)

src = files[-1]
with src.open("r", encoding="utf-8", newline="") as f:
    r = csv.DictReader(f)
    for row in r:
        mid = (row.get("mid") or "").strip()
        if mid.startswith("/m/"):
            title = (row.get("title") or slug).strip()
            print(f"{mid}|{title}")
            sys.exit(0)

print("[ERR] Aucun MID /m/... trouvé")
sys.exit(3)
