# syntax=docker/dockerfile:1
# ============================================================================
# Cloud Run image for the Kronos Forecasting Dashboard.
#
# Notes specific to Cloud Run:
#   - Cloud Run injects $PORT; uvicorn must bind 0.0.0.0:$PORT.
#   - The container filesystem is read-only except /tmp, so the SQLite DB and
#     the HuggingFace cache are pointed at /tmp.
#   - Kronos is cloned at BUILD time (not runtime) and model weights are
#     pre-downloaded into the image so cold starts don't pay that cost.
#   - CPU-only torch (Cloud Run general compute has no GPU). Forecasts are slow
#     (~minutes); raise --timeout and concurrency accordingly when deploying.
# ============================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf_cache \
    KRONOS_DIR=/app/Kronos \
    KRONOS_DEVICE=cpu \
    KRONOS_MODEL=NeoQuasar/Kronos-small \
    KRONOS_TOKENIZER=NeoQuasar/Kronos-Tokenizer-base \
    FORECAST_DB=/tmp/forecasts.db \
    KRONOS_PREWARM=0

WORKDIR /app

# System deps: git to clone Kronos. Build tools only if a wheel needs compiling.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Python deps -----------------------------------------------------------
# CPU-only torch first (smaller, no CUDA), then the rest of the app deps.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

# --- Kronos model code (cloned at build time, baked into the image) --------
RUN git clone --depth 1 https://github.com/shiyu-coder/Kronos.git /app/Kronos

# --- App code --------------------------------------------------------------
COPY . /app

# --- Pre-download model + tokenizer weights into the image -----------------
# So the first request after a cold start doesn't wait on a ~100MB HF download.
RUN python -c "import os,sys; sys.path.insert(0,'/app/Kronos'); \
from model import Kronos, KronosTokenizer; \
KronosTokenizer.from_pretrained(os.environ['KRONOS_TOKENIZER']); \
Kronos.from_pretrained(os.environ['KRONOS_MODEL']); \
print('weights cached into image OK')"

# Cloud Run sets $PORT (default 8080). Bind it.
ENV PORT=8080
EXPOSE 8080

# Single worker: the in-process forecast cache + per-key locks assume one
# process. Scale via Cloud Run instances, not workers.
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT} --workers 1
