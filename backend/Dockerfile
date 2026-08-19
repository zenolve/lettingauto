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

# Install the Chromium browser Playwright drives for the PRIMARY PDF path, so
# downloaded / signed PDFs render pixel-identically to the in-app editor preview
# (both use Chromium). Without the browser binary the app fell back to
# WeasyPrint, which lays the document out differently (UAT feedback #2 / #15).
# --with-deps pulls the browser's own apt dependencies.
RUN python -m playwright install --with-deps chromium

COPY . .

# Ensure the static-mount + signature dirs exist even before volumes attach.
RUN mkdir -p uploads app/templates/signatures

# PDF rendering: the primary path is Chromium (installed above); WeasyPrint
# (system deps installed above) remains as a fallback if Chromium ever fails.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
