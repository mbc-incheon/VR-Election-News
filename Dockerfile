FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY election-data-server election-data-server
COPY election-news-server election-news-server
COPY data data
COPY scripts scripts
COPY fixtures fixtures
COPY election_common.py .
COPY db db
CMD ["python","-m","uvicorn","app:app","--app-dir","election-news-server","--host","0.0.0.0","--port","8102"]
