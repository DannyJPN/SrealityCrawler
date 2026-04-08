FROM python:3.12-slim

# Set timezone
ENV TZ=Europe/Prague
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Flask port
EXPOSE 8000

# Run Flask application (optionally under debugpy)
CMD ["sh", "-c", "if [ \"$DEBUGPY_ENABLE\" = \"1\" ]; then WAIT=\"\"; if [ \"$DEBUGPY_WAIT\" = \"1\" ]; then WAIT=\"--wait-for-client\"; fi; python -m debugpy --listen 0.0.0.0:${DEBUGPY_PORT:-5679} $WAIT -m flask run --host=0.0.0.0 --port=8000; else python -m flask run --host=0.0.0.0 --port=8000; fi"]
