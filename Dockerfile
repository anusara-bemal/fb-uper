FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create downloads directory with proper permissions
RUN mkdir -p /app/downloads && chmod 777 /app/downloads

# Run as non-root user for security
RUN useradd -m appuser
USER appuser

# Command to run the application
CMD ["python", "userbot.py"] 