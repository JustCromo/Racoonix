FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 1000 --create-home racoonix
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER racoonix
EXPOSE 8000
CMD ["sh", "-c", "python -m racoonix.bootstrap && exec gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - wsgi:app"]
