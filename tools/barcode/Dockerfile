FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ghostscript \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "treepoem>=3.23,<4"
RUN useradd --uid 1000 gen
WORKDIR /lavoro
COPY genera_demo.py .
USER gen
ENTRYPOINT ["python", "genera_demo.py"]
