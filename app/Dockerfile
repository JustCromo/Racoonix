FROM python:3.12-slim
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 1000 --create-home racoonix
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER racoonix
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:8000 --workers 2 --worker-tmp-dir /tmp --access-logfile - wsgi:app"]
