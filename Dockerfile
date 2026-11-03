ARG NOPECHA_VERSION=0.6.1

FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Install Python dependencies first (layer cached unless requirements change)
COPY requirements.txt pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

# Bake NopeCHA extension into image (pin version → stable, reproducible builds)
# To upgrade: change NOPECHA_VERSION arg and rebuild
ARG NOPECHA_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends unzip curl \
    && mkdir -p /app/extensions/nopecha \
    && curl -fsSL \
       "https://github.com/NopeCHALLC/nopecha-extension/releases/download/${NOPECHA_VERSION}/chromium.zip" \
       -o /tmp/nopecha.zip \
    && unzip -q /tmp/nopecha.zip -d /app/extensions/nopecha \
    && rm /tmp/nopecha.zip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy runtime files
COPY run.py scan.py ./
COPY templates/ ./templates/

# Data directory created at runtime (mounted from host)
RUN mkdir -p /app/data

CMD ["python", "run.py"]
