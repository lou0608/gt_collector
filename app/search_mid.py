# app/search_mid.py
import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from pytrends.request import TrendReq

# Répertoire de sortie (Docker : monté sur /data)
DATA_DIR = Path(os.getenv("OUTDIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Schéma CSV standardisé ---
CSV_HEADERS = [
    "query",          # terme demandé
    "source",         # kg | pytrends
    "locale",         # langue pour pytrends (ou "*" pour KG)
    "title",          # libellé retourné
    "type",           # type "topic" | "keyword"
    "schema_types",   # types KG concaténés par "|"
    "mid",            # id /m/...
    "confidence",     # score (float 0-1 si KG ; 1.0 par défaut pour pytrends)
]

# --- Locales pour le fallback Pytrends (on ne traduit PAS le terme) ---
LOCALES = ["fr-FR", "en-US", "en-GB", "de-DE", "es-ES", "it-IT", "pt-PT"]

# --- Types/indices à exclure explicitement (sécurité "anti-musique", etc.) ---
NEGATIVE_TYPES = {
    "MusicRecording", "MusicAlbum", "Song", "TVEpisode", "Movie",
    "VideoGame", "VideoGameSeries", "Book", "MusicalArtist"
}

# --- Heuristiques "médical" ---
MEDICAL_KEYWORDS = {
    "medical", "medicine", "disease", "syndrome", "disorder", "illness",
    "cardio", "infection", "pathology", "symptom", "treatment", "anatomy",
    "organ", "infarct", "stroke", "hypertension", "arrhythmia",
    "maladie", "pathologie", "symptôme", "traitement", "organe",
    "infarctus", "AVC", "hypertension", "arythmie", "cardiaque", "cardiologie"
}
MEDICAL_TYPES = {
    "MedicalCondition", "MedicalSignOrSymptom", "MedicalTherapy",
    "AnatomicalStructure", "MedicalEntity", "PathologyTest", "Drug"
}


def _slugify(label: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in label)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def is_medical(row: Dict[str, Any]) -> bool:
    # 1) Types KG
    types = (row.get("schema_types") or "")
    if types:
        if any(t in MEDICAL_TYPES for t in types.split("|")):
            return True
    # 2) Titre + Description (quand présent)
    title = (row.get("title") or "").lower()
    desc = (row.get("description") or "").lower()
    text = f"{title} {desc}"
    return any(k in text for k in MEDICAL_KEYWORDS)


def kg_lookup(query: str,
              api_key: str,
              languages: Optional[List[str]] = None,
              limit: int = 10,
              types_hint: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Recherche dans Google Knowledge Graph.
    Retourne une liste normalisée de lignes compatibles CSV_HEADERS.
    """
    rows: List[Dict[str, Any]] = []
    langs = languages or ["fr", "en"]

    for lang in langs:
        # Paramètres KG
        params = {
            "query": query,
            "key": api_key,
            "limit": limit,
            "languages": lang,
        }
        if types_hint:
            # Il n'y a pas de param "types" officiel multiple ; on filtre ensuite.
            pass

        try:
            r = requests.get(
                "https://kgsearch.googleapis.com/v1/entities:search",
                params=params,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            # On log soft et on continue sur la langue suivante
            print(f"[WARN] KG error ({lang}) : {e}")
            continue

        for item in data.get("itemListElement", []):
            res = item.get("result", {})
            score = float(item.get("resultScore") or 0.0)
            mid = res.get("@id", "")  # ex: "kg:/m/01234"
            if mid.startswith("kg:"):
                mid = mid[3:]
            name = res.get("name", "")
            desc = res.get("description", "") or ""
            types = res.get("@type", []) or []
            # Filtrage éventuel par types_hint
            if types_hint and not any(t in types for t in types_hint):
                continue
            # Exclusion NEGATIVE_TYPES
            if any(t in NEGATIVE_TYPES for t in types):
                continue

            rows.append({
                "query": query,
                "source": "kg",
                "locale": "*",
                "title": name,
                "type": "topic" if mid.startswith("/m/") else "keyword",
                "schema_types": "|".join(types),
                "mid": mid if mid.startswith("/m/") else "",
                "confidence": f"{min(score/100.0, 1.0):.6f}",
                "description": desc,  # champ auxiliaire interne (non écrit)
            })

    # Déduplication par MID en gardant le score max
    best_by_mid: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        mid = r.get("mid", "")
        if not mid:
            # pour KG on exige un MID
            continue
        cur = best_by_mid.get(mid)
        sc = float(r.get("confidence") or 0.0)
        if (cur is None) or (sc > float(cur.get("confidence") or 0.0)):
            best_by_mid[mid] = r
    return list(best_by_mid.values())


def pytrends_suggestions_exact(query: str, locales: List[str]) -> List[Dict[str, Any]]:
    """
    Fallback : Pytrends suggestions(query) pour plusieurs locales.
    On NE traduit PAS le terme : on teste le même 'query' sur différentes locales.
    """
    out: List[Dict[str, Any]] = []

    for loc in locales:
        try:
            pytr = TrendReq(hl=loc, tz=0)
            sugg = pytr.suggestions(query) or []
        except Exception as e:
            print(f"[WARN] pytrends({loc}) error: {e}")
            continue

        for s in sugg:
            # pytrends renvoie : {'title','type','mid','mid','...'}
            title = s.get("title", "")
            typ = s.get("type", "") or "keyword"
            mid = s.get("mid", "") or ""
            # On ne peut pas inférer schema_types ; on laisse vide.
            # Exclusion basique : si pas de MID, on garde quand même (keyword),
            # car ça peut être utile pour un second passage manuel.
            out.append({
                "query": query,
                "source": "pytrends",
                "locale": loc,
                "title": title,
                "type": "topic" if mid.startswith("/m/") else "keyword",
                "schema_types": "",
                "mid": mid,
                "confidence": "1.0",
            })

        # petit throttle pour éviter des 429 en rafale
        time.sleep(0.4)

    # Déduplication : prioriser entrées avec MID
    best: Dict[str, Dict[str, Any]] = {}
    # 1) garder tous les avec MID (clé = MID)
    for r in [x for x in out if x.get("mid")]:
        mid = r["mid"]
        if mid not in best:
            best[mid] = r
    # 2) Ajouter quelques "keywords" sans MID distincts par titre
    seen_titles = {r["title"].lower() for r in best.values()}
    for r in [x for x in out if not x.get("mid")]:
        t = r["title"].lower()
        if t and t not in seen_titles:
            best[t] = r
            seen_titles.add(t)

    return list(best.values())


def write_rows(path: Path, rows: List[Dict[str, Any]], append: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or not append
    with path.open("a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if write_header:
            w.writeheader()
        for r in rows:
            # n’écrivons que les colonnes officielles
            w.writerow({k: r.get(k, "") for k in CSV_HEADERS})
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Recherche de MIDs (topics) pour des mots-clés, sortie CSV.")
    parser.add_argument("--query", "-q", action="append",
                        help="Mot-clé (répéter l’option pour plusieurs)", required=True)
    parser.add_argument(
        "--outfile", help="Forcer un fichier de sortie unique (mode legacy).")
    parser.add_argument("--append", action="store_true",
                        help="Ajouter à la fin du fichier si --outfile est utilisé.")
    parser.add_argument("--kg-langs", default="fr,en",
                        help="Langues KG (liste séparée par virgules).")
    parser.add_argument("--kg-types", default="",
                        help="Types KG à favoriser (ex: MedicalCondition,Drug)")
    parser.add_argument("--prefer-mids", action="store_true",
                        help="Ne garder que les résultats avec MID /m/...")
    parser.add_argument("--filter-medical", action="store_true",
                        help="Ne garder que les résultats médicaux.")
    args = parser.parse_args()

    queries = [q.strip() for q in args.query if q and q.strip()]
    if not queries:
        print("[ERR] Aucun terme fourni.")
        return

    kg_key = os.getenv("GOOGLE_API_KEY", "").strip()
    kg_langs = [x.strip() for x in args.kg_langs.split(",") if x.strip()]
    kg_types = [x.strip() for x in args.kg_types.split(",") if x.strip()]

    out_override: Optional[Path] = None
    if args.outfile:
        out_override = Path(args.outfile)
        out_override.parent.mkdir(parents=True, exist_ok=True)

    for q in queries:
        rows: List[Dict[str, Any]] = []

        # 1) Essai KG si clé présente
        if kg_key:
            rows = kg_lookup(q, kg_key, languages=kg_langs,
                             types_hint=kg_types if kg_types else None)

        # 2) Fallback Pytrends si rien trouvé
        if not rows:
            rows = pytrends_suggestions_exact(q, LOCALES)

        # 3) Filtres négatifs génériques
        safe_rows: List[Dict[str, Any]] = []
        for r in rows:
            types = (r.get("schema_types") or "")
            if any(t in NEGATIVE_TYPES for t in types.split("|") if t):
                continue
            safe_rows.append(r)
        rows = safe_rows

        # 4) Filtres optionnels
        if args.prefer_mids:
            rows = [r for r in rows if (r.get("mid") or "").startswith("/m/")]
        if args.filter_medical:
            rows = [r for r in rows if is_medical(r)]

        # 5) Finalisation + écriture
        run_date = datetime.now().strftime("%YMMDD")  # volontairement YYYYMMDD
        # correction format (bugfix) : %m pour mois, %d pour jour
        run_date = datetime.now().strftime("%Y%m%d")

        if out_override:
            out_path = out_override
            written = write_rows(out_path, rows, append=args.append)
        else:
            q_slug = _slugify(q)
            out_path = DATA_DIR / \
                f"topics_suggestions__{q_slug}__{run_date}.csv"
            written = write_rows(out_path, rows, append=False)

        print(f"[OK] {written} lignes écrites → {out_path}")

    print("[DONE]")


if __name__ == "__main__":
    main()
