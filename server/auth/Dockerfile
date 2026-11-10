FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/app/shared
WORKDIR /app


COPY auth/requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY shared/ieumsae_shared /app/shared/ieumsae_shared
COPY auth/ieumsae_auth /app/ieumsae_auth
COPY auth/attestation_roots /app/attestation_roots
COPY tools/secret_loader.py /app/secret_loader.py

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8000
CMD ["python", "-m", "ieumsae_shared.runtime", "auth"]
