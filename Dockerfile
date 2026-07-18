FROM python:3.14-slim

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY requirements.txt ./
RUN python -m ensurepip --upgrade && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    python -m pip uninstall -y pip setuptools

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser migrations/ ./migrations/
COPY --chown=appuser:appuser alembic.ini ./
RUN chmod +x scripts/entrypoint.sh

RUN mkdir -p /app/db /logs && chown appuser:appuser /app/db /logs

ENV PYTHONPATH="/app/src"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"]

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
