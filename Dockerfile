# ---- Build stage: install dependencies into a self-contained venv ----
FROM python:3.12-slim-bookworm AS build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

# ---- Final stage: runtime only ----
FROM python:3.12-slim-bookworm

# Patch OS packages at build time.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin departed

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEPARTED_DATA_DIR=/data \
    DEPARTED_PORT=8080

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY run.py VERSION ./

RUN mkdir -p /data && chown -R 1000:1000 /data /app

USER 1000
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=8)" || exit 1

CMD ["python", "run.py"]
