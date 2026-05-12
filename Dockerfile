# ============================== Initial Building =============================
FROM python:3.11.14-slim-bookworm AS builder

WORKDIR /app

# CPU-only PyTorch
RUN pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ============================== Size Reduction ===============================
FROM python:3.11.14-slim-bookworm

WORKDIR /app

# Only necessary dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# System dependencies for runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ============================ Final Compilation ==============================
COPY . .

EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:7860/health || exit 1

CMD ["python", "main.py", "--app", "de"]
