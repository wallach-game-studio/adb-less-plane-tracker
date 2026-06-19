FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/ web/
COPY tracker/ tracker/
COPY config.yaml .

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
