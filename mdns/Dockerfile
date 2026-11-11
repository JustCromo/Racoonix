FROM python:3.12-slim
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir zeroconf==0.151.0
COPY annuncia.py /srv/annuncia.py
USER 65534:65534
CMD ["python", "/srv/annuncia.py"]
