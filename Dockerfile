# Dockerfile
FROM python:3.11-slim

# Bonnes pratiques Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY app/ ./app
COPY scripts/ ./scripts

# Healthcheck : vérifie toutes les 2 minutes, tolère 2 échecs, timeout 10s
HEALTHCHECK --interval=2m --timeout=10s --retries=2 \
    CMD python -m app.tools.healthcheck || exit 1

# Commande par défaut (sera écrasée par `docker compose run ...`)
CMD ["python", "-m", "app.main"]
