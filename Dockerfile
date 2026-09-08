FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROOFBOUND_ENV=production \
    PROOFBOUND_PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt
COPY proofbound/ proofbound/
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "proofbound.cli.main", "serve", "--host", "0.0.0.0", "--port", "8000"]
