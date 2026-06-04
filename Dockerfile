FROM python:3.12-slim

# Install system dependencies for Whisper (ffmpeg) and audio processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir "setuptools<70.0.0" wheel
RUN pip install --no-cache-dir --no-build-isolation -r requirements.txt

# Copy application code
COPY . .

# Create storage directories
RUN mkdir -p /app/storage/audio /app/storage/transcripts

EXPOSE 8000
