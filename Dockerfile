FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/sciwork/argus"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000"]
