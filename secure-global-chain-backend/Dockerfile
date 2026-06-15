FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package and its dependencies (wheels only; no build toolchain
# needed for numpy/scipy/ortools/asyncpg/cryptography on linux x86_64).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Migrations live outside the package; copy them for `alembic upgrade head`.
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

CMD ["uvicorn", "sgc.main:app", "--host", "0.0.0.0", "--port", "8000"]
