FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

# Puerto donde escucha la aplicación (hay que indicarlo también en Coolify)
EXPOSE 8000

# Crea/actualiza las tablas de la base y arranca el servidor
CMD ["sh", "-c", "python manage.py migrate && gunicorn sistema.wsgi:application --bind 0.0.0.0:8000"]
