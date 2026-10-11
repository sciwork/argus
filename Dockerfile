FROM node:22-slim AS frontend-build

WORKDIR /frontend
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend ./
RUN pnpm build


FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/sciwork/argus"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=frontend-build /frontend/out ./src/argus/dashboard/frontend

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000"]
