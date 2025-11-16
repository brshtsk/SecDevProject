# Base stage
ARG PY_IMAGE=python:3.11-slim@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

FROM ${PY_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Test stage
FROM base AS test
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt
COPY . .
RUN pytest -q

# Dependencies stage
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target /opt/site-packages

# Runtime stage
FROM ${PY_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/site-packages
WORKDIR /app

# Непривелегированный пользователь для запуска
RUN groupadd -g 1000 app && useradd -m -u 1000 -g 1000 -s /usr/sbin/nologin app

# Рантайм-зависимости и код
COPY --from=deps --chown=app:app /opt/site-packages /opt/site-packages
COPY --chown=app:app app/ app/
COPY --chown=app:app scripts/ scripts/

# Entrypoint-скрипт (LF и исполняемые права на Windows-хосте)
COPY --chown=app:app scripts/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys,urllib.request; exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).getcode()==200 else sys.exit(1)"

USER app

ENTRYPOINT ["/entrypoint.sh"]
