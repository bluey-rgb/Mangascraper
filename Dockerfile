# A small image that runs the Manga Tracker web app.
FROM python:3.12-slim

# Don't write .pyc files; show logs immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY app ./app

# The database lives here; docker-compose mounts a volume so it persists.
ENV DB_PATH=/app/data/manga.db
RUN mkdir -p /app/data

EXPOSE 8000

# Serve the app. Uvicorn listens on all interfaces so the container is reachable.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
