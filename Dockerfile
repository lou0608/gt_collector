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

# Healthcheck (si app.healthcheck existe vraiment)
HEALTHCHECK --interval=5m --timeout=10s CMD python -m app.healthcheck || exit 1

# Commande par défaut (sera écrasée par `docker compose run ...`)
CMD ["python", "-m", "app.main"]
