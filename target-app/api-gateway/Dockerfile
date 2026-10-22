FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install stress-ng and procps for safe, bounded CPU/memory stress testing
RUN apt-get update && apt-get install -y --no-install-recommends stress-ng procps && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py fault_interceptor.py faultlab_stress.py ./

EXPOSE 8000

CMD ["python", "app.py"]
