FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

WORKDIR /data
EXPOSE 8765
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
