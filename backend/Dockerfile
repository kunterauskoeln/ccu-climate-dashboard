FROM python:3.15-slim

WORKDIR /app

# Dependencies installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend-Code kopieren
COPY src/app ./app

# Read-only Diagnose-Skripte (docker compose exec backend python scripts/dump_ccu.py ...)
COPY scripts ./scripts

# Startbefehl
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

