# Pinned to bookworm so the WeasyPrint system-dep package names below stay
# stable (newer Debian renamed libgdk-pixbuf2.0-0 -> libgdk-pixbuf-2.0-0).
FROM python:3.11-slim-bookworm

# WeasyPrint system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
      shared-mime-info fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Ensure the static-mount + signature dirs exist even before volumes attach.
RUN mkdir -p uploads app/templates/signatures

# PDF rendering falls back to WeasyPrint (system deps installed above) when the
# Chromium primary path is unavailable — no browser binary needed in the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
