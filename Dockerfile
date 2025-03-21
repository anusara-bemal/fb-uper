FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code and cookies
COPY youtube_to_facebook_new.py .
COPY youtube_cookies.txt .
COPY .env .
COPY videos.txt .

# Create downloads directory
RUN mkdir -p downloads

# Command to run the bot
CMD ["python", "youtube_to_facebook_new.py"] 
