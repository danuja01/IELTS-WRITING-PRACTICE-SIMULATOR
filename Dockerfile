FROM python:3.12-alpine
WORKDIR /app
ARG APP_VERSION=3.0.1
LABEL org.opencontainers.image.version="${APP_VERSION}"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
ENV PORT=5050
ENV APP_VERSION=${APP_VERSION}
EXPOSE 5050
# Defaults preserve current prod: 1 worker, 1 thread (override via GUNICORN_* env)
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-1} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile - --error-logfile - app:app"]
