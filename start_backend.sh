#!/usr/bin/env bash
# macOS / Linux equivalent of start_backend.bat
cd "$(dirname "$0")/backend" && source .venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
