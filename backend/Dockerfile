FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 alianza \
    && mkdir -p /app/uploads \
    && chown -R alianza:alianza /app
COPY --chown=alianza:alianza backend/ .
COPY --chown=alianza:alianza frontend/src/assets/logo_cert.png /app/app/assets/logo_cert.png

USER alianza

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "8", "--timeout", "600", "--worker-tmp-dir", "/dev/shm", "wsgi:app"]
