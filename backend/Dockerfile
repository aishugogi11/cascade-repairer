FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --timeout 120 --retries 3 -r requirements.txt

COPY . .

CMD ["python", "main.py"]


