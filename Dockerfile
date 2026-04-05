FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY src/ src/

RUN mkdir -p /data

EXPOSE 50005 4040

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/pool.db
ENV PROXY_PORT=50005
ENV WEB_PORT=4040

CMD ["python3", "-m", "src.main"]
