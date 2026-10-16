FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home app
COPY . .
RUN mkdir -p /data/media /app/staticfiles && chown -R app:app /app /data
USER app
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn campus.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 --access-logfile /dev/null --error-logfile -"]
