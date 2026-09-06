FROM python:3.12-slim
WORKDIR /app
COPY requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt
COPY src ./src
COPY main.py ./main.py
ENV PYTHONPATH=/app
CMD ["uvicorn", "src.service.api:app", "--host", "0.0.0.0", "--port", "8000"]
