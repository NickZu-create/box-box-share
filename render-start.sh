#!/bin/sh
# Render start command: migrate, clean up, optionally create the admin from DJANGO_SUPERUSER_* variables, then serve.
set -e
python manage.py migrate --noinput
# Render free has no cron; each start also clears expired tokens and GPA proofs past retention.
python manage.py cleanup_auth || true
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then python manage.py createsuperuser --noinput || true; fi
exec gunicorn campus.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60 --access-logfile /dev/null --error-logfile -
