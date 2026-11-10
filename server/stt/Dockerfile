FROM pytorch/pytorch:2.13.0-cuda12.6-cudnn9-runtime@sha256:6acf597eeb8e376a96580dde4952f37cc017fef732bb40bfc73f28f25e3f64b4

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/app/shared
RUN python -m venv --without-pip --system-site-packages /opt/ieumsae-venv
ENV PATH="/opt/ieumsae-venv/bin:${PATH}"
WORKDIR /app


COPY stt/torchaudio.lock stt/requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps --index-url https://download.pytorch.org/whl/cpu -r torchaudio.lock  && python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY shared/ieumsae_shared /app/shared/ieumsae_shared
COPY stt/ieumsae_stt /app/ieumsae_stt

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8000

CMD ["python", "-m", "ieumsae_shared.runtime", "stt"]
