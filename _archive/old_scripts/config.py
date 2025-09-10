import os

KEYWORDS = [k.strip() for k in os.getenv(
    "KEYWORDS", "cardiologie,cardiology").split(",")]
GEO = os.getenv("GEO", "FR")
TIMEFRAME = os.getenv("TIMEFRAME", "now 7-d")
CSV_PATH = os.getenv("CSV_PATH", "/data/trends.csv")
MON_PATH = os.getenv("MON_PATH", "/data/monitoring_runs.csv")
