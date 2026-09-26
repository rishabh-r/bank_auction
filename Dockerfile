# Multi-stage: build deps in one layer, ship a smaller runtime image.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .


FROM python:3.12-slim AS runtime

# Never run as root.
RUN useradd --create-home --uid 10001 auction

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Kolkata

COPY --from=builder /opt/venv /opt/venv
COPY --chown=auction:auction migrations /app/migrations
COPY --chown=auction:auction alembic.ini /app/alembic.ini

WORKDIR /app
USER auction

# The archive of raw documents. Mount a volume here in production; on a
# real deployment this becomes S3.
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/api/health', timeout=4).status_code==200 else 1)"

CMD ["uvicorn", "auction_portal.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
