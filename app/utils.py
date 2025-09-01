# app/utils.py
import csv
import time
import argparse
from pathlib import Path
from pytrends.request import TrendReq

ALLOWED_TYPES = {
    "Medical condition", "Medical Condition", "Disease", "Symptom",
    "Field of study", "Topic"
}


def resolve_mid(query: str, expected_type: str | None = None):
    py = TrendReq(hl="fr-FR", tz=0)
    suggestions = py.suggestions(query)
    if not suggestions:
        return None
    if expected_type:
        c = [s for s in suggestions if s.get("type") == expected_type]
        if c:
            s = c[0]
            return s["mid"], s["title"], s["type"]
    c = [s for s in suggestions if s.get("type") in ALLOWED_TYPES]
    if c:
        s = c[0]
        return s["mid"], s["title"], s["type"]
    s = suggestions[0]
    return s["mid"], s["title"], s.get("type")


def build_topics_resolved(in_csv="/data/meta/topics.csv", out_csv="/data/meta/topics_resolved.csv", sleep_s=1.0):
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(in_csv, newline="", encoding="utf-8") as fin, \
            open(out_csv, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        fieldnames = ["query", "label", "expected_type",
                      "mid", "resolved_title", "resolved_type"]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            if row.get("enabled") not in ("1", "true", "True"):
                continue
            q = (row.get("query") or "").strip()
            label = (row.get("label") or "").strip()
            exp = (row.get("expected_type") or "").strip() or None
            res = resolve_mid(q, exp)
            if res is None:
                writer.writerow({"query": q, "label": label, "expected_type": exp or "",
                                 "mid": "", "resolved_title": "", "resolved_type": ""})
            else:
                mid, title, rtype = res
                writer.writerow({"query": q, "label": label, "expected_type": exp or "",
                                 "mid": mid, "resolved_title": title, "resolved_type": rtype or ""})
            count += 1
            time.sleep(sleep_s)  # anti-429
    print(f"[OK] {out_csv} généré ({count} lignes lues).")


def main():
    p = argparse.ArgumentParser(
        description="Résout les MIDs de topics.csv vers topics_resolved.csv")
    p.add_argument("--in", dest="in_csv", default="/data/meta/topics.csv",
                   help="Chemin d'entrée topics.csv")
    p.add_argument("--out", dest="out_csv",
                   default="/data/meta/topics_resolved.csv", help="Chemin de sortie")
    p.add_argument("--sleep", dest="sleep_s", type=float,
                   default=1.0, help="Pause entre requêtes (anti-429)")
    args = p.parse_args()
    build_topics_resolved(in_csv=args.in_csv,
                          out_csv=args.out_csv, sleep_s=args.sleep_s)


if __name__ == "__main__":
    main()
