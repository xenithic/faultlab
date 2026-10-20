FROM python:3.12-slim

WORKDIR /app

# Ensure Python output is sent straight to terminal/logs without buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5004

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5004

CMD ["python", "app.py"]
