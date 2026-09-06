FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY docker-entrypoint.sh /usr/local/bin/cookbook-entrypoint

WORKDIR /data
EXPOSE 8765
ENTRYPOINT ["sh", "/usr/local/bin/cookbook-entrypoint"]
