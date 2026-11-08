# N² Extraction Arena: one image with the FastAPI backend, the built React frontend and Tesseract OCR.
#
#   docker build -t n2-extraction-arena .
#   docker run --rm -p 8000:8000 --env-file .env -v n2-data:/data n2-extraction-arena
#   open http://localhost:8000

# ---- 1. Build the frontend -------------------------------------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Runtime: Python backend + Tesseract --------------------------------
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Uploads and the SQLite database live in /data (mount a volume to keep them between runs).
ENV STATIC_DIR=/app/frontend/dist \
    DATA_DIR=/data
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app:app /data
USER app
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
