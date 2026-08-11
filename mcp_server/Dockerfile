FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

# Cloud Run injects $PORT; server.py already reads it. EXPOSE is documentation.
EXPOSE 8080
CMD ["python", "server.py"]