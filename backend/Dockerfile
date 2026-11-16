FROM python:3.12-slim
WORKDIR /app/backend
COPY requirements.txt /tmp/requirements.txt
RUN pip install --default-timeout=1000 --retries=5 --no-cache-dir -r /tmp/requirements.txt
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
