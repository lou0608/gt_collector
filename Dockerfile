FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=5m --timeout=10s CMD python -m app.healthcheck || exit 1
CMD ["python", "-m", "app.main"]

