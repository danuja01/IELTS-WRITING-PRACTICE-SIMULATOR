FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
ENV PORT=5050
EXPOSE 5050
CMD ["python", "app.py"]
