FROM python:3.12-alpine
WORKDIR /app
ARG APP_VERSION=2.0.17
LABEL org.opencontainers.image.version="${APP_VERSION}"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
ENV PORT=5050
ENV APP_VERSION=${APP_VERSION}
EXPOSE 5050
# 1 worker + 1 thread: SQLite is one file; avoids lock errors with multiple browsers
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 1 --timeout 120 --access-logfile - --error-logfile - app:app"]
