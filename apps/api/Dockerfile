FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

COPY packages/runway_core /app/packages/runway_core
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
COPY samples /app/samples
COPY apps/ui/public /app/apps/ui/public
COPY apps/api/app /app/apps/api/app
COPY scripts /app/scripts
COPY apps/api/entrypoint.sh /app/apps/api/entrypoint.sh

RUN pip install --no-cache-dir -e /app/packages/runway_core \
  && pip install --no-cache-dir -r /app/apps/api/requirements.txt \
  && sed -i 's/\r$//' /app/apps/api/entrypoint.sh \
  && chmod +x /app/apps/api/entrypoint.sh

WORKDIR /app/apps/api
ENV PYTHONPATH=/app/apps/api
ENV PYTHONUNBUFFERED=1
ENV RUNWAY_PRICING_OVERRIDES=/app/samples/pricing_overrides.json

EXPOSE 8000

ENTRYPOINT ["/app/apps/api/entrypoint.sh"]
