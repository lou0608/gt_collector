# app/next_topic.py
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from app.paths import CONFIG_DIR, STATE_DIR, ensure_dirs


def _read_topics(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier topics introuvable: {path}")
    topics: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        topics.append(line)
    if not topics:
        raise ValueError(f"Aucun topic valide dans {path}")
    return topics


def _load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    # index = -1 pour que le premier appel sélectionne topics[0]
    return {"index": -1, "history": []}


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(
        state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_next_topic(topics: List[str], state: dict) -> tuple[str, int]:
    next_idx = (int(state.get("index", -1)) + 1) % len(topics)
    topic = topics[next_idx]
    return topic, next_idx


def main() -> None:
    # Crée OUTDIR/{config,state,logs,processed} selon app.paths
    ensure_dirs()

    parser = argparse.ArgumentParser(
        description="Sélectionne le prochain topic et met à jour le pointeur.")
    # Defaults = OUTDIR via app.paths (CONFIG_DIR/STATE_DIR)
    parser.add_argument(
        "--topics-file", default=str(CONFIG_DIR / "topics.txt"))
    parser.add_argument(
        "--state-file",  default=str(STATE_DIR / "topic_pointer.json"))
    parser.add_argument(
        "--out-file",    default=str(CONFIG_DIR / "_current_topic.txt"))
    args = parser.parse_args()

    topics_file = Path(args.topics_file)
    state_file = Path(args.state_file)
    out_file = Path(args.out_file)

    # Logs de debug explicites
    print(f"[NEXT_TOPIC] topics_file = {topics_file}")
    print(f"[NEXT_TOPIC] state_file  = {state_file}")
    print(f"[NEXT_TOPIC] out_file    = {out_file}")

    topics = _read_topics(topics_file)
    state = _load_state(state_file)
    topic, idx = pick_next_topic(topics, state)

    now_utc = datetime.now(timezone.utc).isoformat()
    state["index"] = idx
    state.setdefault("history", [])
    state["history"].append({
        "ts_utc": now_utc,
        "topic": topic,
        "index": idx,
        "total_topics": len(topics),
    })
    _save_state(state_file, state)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(topic + "\n", encoding="utf-8")

    print(f"[NEXT_TOPIC] Sélectionné : {topic}")
    print(f"[NEXT_TOPIC] Écrit dans  : {out_file}")

    # Compat : dernière ligne = uniquement le topic
    print(topic)


if __name__ == "__main__":
    main()
