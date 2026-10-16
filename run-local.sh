#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3.12}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required (3.12 recommended)"'
if [ ! -d .venv ]; then "$PYTHON" -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python manage.py migrate --noinput
exec .venv/bin/python manage.py runserver 127.0.0.1:8000
