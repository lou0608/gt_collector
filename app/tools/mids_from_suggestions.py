# app/tools/mids_from_suggestions.py
from pathlib import Path
import csv
import sys

DATA = Path("/data")


def mids_from_csv(keyword_slug: str) -> int:
    # Prend le plus récent CSV correspondant
    files = sorted(DATA.glob(f"topics_suggestions__{keyword_slug}__*.csv"))
    if not files:
        print(f"[ERR] Aucun fichier pour {keyword_slug}")
        return 0
    src = files[-1]
    out = DATA / f"mids__{keyword_slug}.txt"

    mids = []
    with src.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            mid = (row.get("mid") or "").strip()
            if mid.startswith("/m/"):
                mids.append(mid)

    mids = sorted(set(mids))
    out.write_text("\n".join(mids), encoding="utf-8")
    print(f"[OK] {len(mids)} MID(s) → {out}")
    return len(mids)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.tools.mids_from_suggestions <slug-mot-cle>")
        sys.exit(1)
    mids_from_csv(sys.argv[1])
