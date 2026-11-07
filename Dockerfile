FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src CMAKE_BUILD_PARALLEL_LEVEL=2
COPY config/requirements.lock config/voice-requirements.lock config/requirements-llm.lock ./config/
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng build-essential cmake && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r config/requirements.lock -r config/voice-requirements.lock -r config/requirements-llm.lock
COPY src ./src
COPY models ./models
COPY resources/recordings ./resources/recordings
COPY resources/examples ./resources/examples
COPY scripts/start_app.sh scripts/prepare_voice.py scripts/prepare_query_model.py ./scripts/
ENV SCHOLARGRAPH_VOSK_MODEL=/opt/voice/vosk-en SCHOLARGRAPH_PIPER_MODEL=/opt/voice/piper/en_US-ljspeech-medium.onnx \
    SCHOLARGRAPH_QUERY_MODEL_PATH=/opt/models/query-understanding.gguf SCHOLARGRAPH_CHAT_MODEL_PATH=/opt/models/query-understanding.gguf
RUN python scripts/prepare_voice.py && python -m piper.download_voices --data-dir /opt/voice/piper en_US-ljspeech-medium \
    && python scripts/prepare_query_model.py --out /opt/models/query-understanding.gguf
EXPOSE 8000
CMD ["sh", "scripts/start_app.sh"]
