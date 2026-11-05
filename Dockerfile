FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
COPY config/requirements.lock ./config/requirements.lock
RUN pip install --no-cache-dir -r config/requirements.lock
COPY src ./src
COPY models ./models
COPY resources/recordings ./resources/recordings
COPY resources/examples ./resources/examples
COPY scripts/start_app.sh ./scripts/start_app.sh
EXPOSE 8000
CMD ["sh", "scripts/start_app.sh"]
