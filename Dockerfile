# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS builder

ARG PYLABVIEW_COMMIT=69768647c18d2d792a259b69884b2433761c3a4f
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN sed -i "s/@69768647c18d2d792a259b69884b2433761c3a4f/@${PYLABVIEW_COMMIT}/" /tmp/requirements.txt \
    && pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    WORK_ROOT=/data/jobs \
    PYLABVIEW_COMMAND=readRSRC \
    PORT=8080

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app /data/jobs \
    && chown -R app:app /app /data

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app app ./app
COPY --chown=app:app main.py ./main.py
COPY --chown=app:app pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./

USER app
EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3); d=json.load(r); raise SystemExit(0 if d.get('pylabview',{}).get('available') else 1)"

CMD ["python", "main.py"]
