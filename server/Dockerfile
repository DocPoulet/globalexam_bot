FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/server/requirements.txt
COPY src /app/src
COPY server /app/server
ENV PYTHONPATH=/app:/app/src PYTHONUNBUFFERED=1
# Railway injecte PORT ; Docker Compose conserve 8000 par défaut.
# L'app n'embarque ni la BDD, ni des profils ou données des utilisateurs.
EXPOSE 8000
USER 65532:65532
CMD ["sh", "-c", "exec uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --no-access-log"]
