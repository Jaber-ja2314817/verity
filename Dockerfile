# --- build frontend ---
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- runtime ---
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/seed ./seed
COPY eval/results/latest.json ./eval/results/latest.json
COPY --from=web /web/dist ./app/static
RUN useradd -m verity && mkdir -p /data && chown -R verity /data /app
USER verity
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
