FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS dependencies
WORKDIR /app
COPY requirements-service.lock.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-service.lock.txt

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=dependencies /wheels /wheels
RUN pip install --no-cache-dir --no-index /wheels/* && rm -rf /wheels && useradd --uid 10001 --create-home app
COPY src ./src
COPY main.py ./main.py
ENV PYTHONPATH=/app
USER app
CMD ["uvicorn", "src.service.api:app", "--host", "0.0.0.0", "--port", "8000"]
