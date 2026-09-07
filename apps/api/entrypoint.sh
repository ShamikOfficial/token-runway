#!/bin/sh
set -e

echo "Waiting for Floci at ${AWS_ENDPOINT_URL:-http://floci:4566} ..."
i=0
until python -c "
import os, urllib.request
url = os.environ.get('AWS_ENDPOINT_URL', 'http://floci:4566').rstrip('/') + '/_floci/health'
urllib.request.urlopen(url, timeout=2)
" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "Floci did not become ready in time"
    exit 1
  fi
  sleep 1
done

echo "Seeding tables + bucket..."
python /app/scripts/seed_floci.py

echo "Starting TokenRunway API..."
cd /app/apps/api
if [ "${RUNWAY_RELOAD:-0}" = "1" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
    --reload-dir /app/apps/api/app --reload-dir /app/packages/runway_core
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
