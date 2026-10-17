FROM python:3.12-slim AS dependencies
WORKDIR /app
COPY requirements-service.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-service.txt

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=dependencies /wheels /wheels
RUN pip install --no-cache-dir --no-index /wheels/* && rm -rf /wheels && useradd --uid 10001 --create-home app
COPY src ./src
COPY main.py ./main.py
ENV PYTHONPATH=/app
USER app
CMD ["uvicorn", "src.service.api:app", "--host", "0.0.0.0", "--port", "8000"]
