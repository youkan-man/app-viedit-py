FROM python:3.12-slim

ARG APP_VERSION=1.0.0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIEDIT_DATA_DIR=/data/jobs \
    VIEDIT_DEFAULT_TEXT_ENCODING=shift_jis \
    VIEDIT_MAX_UPLOAD_BYTES=134217728 \
    VIEDIT_MAX_XML_EDITOR_BYTES=8388608 \
    VIEDIT_COMMAND_TIMEOUT_SECONDS=180 \
    VIEDIT_JOB_TTL_SECONDS=86400 \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN addgroup --system viedit \
    && adduser --system --ingroup viedit --home /nonexistent --no-create-home viedit \
    && mkdir -p /data/jobs \
    && chown -R viedit:viedit /data

USER viedit
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
