from pathlib import Path
import time
import sys
import os

CSV_PATH = os.getenv("CSV_PATH", "/data/trends.csv")
p = Path(CSV_PATH)
ok = p.exists() and p.stat().st_size > 100 and (
    time.time() - p.stat().st_mtime) < 3600
sys.exit(0 if ok else 1)
