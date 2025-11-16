#!/bin/sh
set -e
python -m scripts.prestart
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
