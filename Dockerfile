FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

# Run the watcher as a foreground process (PID 1) so the container restart
# policy governs recovery.
CMD ["spam-watcher"]
