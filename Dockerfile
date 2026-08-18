FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cgvwatch/ cgvwatch/
COPY run.py .

ENV CGVWATCH_DATA=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"

CMD ["python", "run.py"]
