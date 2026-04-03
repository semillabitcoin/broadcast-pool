FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc pkg-config libsecp256k1-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local
# Copy libsecp256k1 shared library from builder
COPY --from=builder /usr/lib/*/libsecp256k1* /usr/lib/

COPY src/ src/

RUN mkdir -p /data && chown 1000:1000 /data

USER 1000:1000

EXPOSE 50005 3080

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/pool.db
ENV PROXY_PORT=50005
ENV WEB_PORT=3080

CMD ["python3", "-m", "src.main"]
