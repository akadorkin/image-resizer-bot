# Use the official Python 3.9 slim image
FROM python:3.9-slim

# Enable contrib and non-free repositories
RUN echo "deb http://deb.debian.org/debian bullseye main contrib non-free" > /etc/apt/sources.list

# Update package list and install necessary dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    unrar \
    && rm -rf /var/lib/apt/lists/*

# Create a user for running the application
RUN useradd -ms /bin/bash celeryuser

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create and set permissions for the temp directory
RUN mkdir -p /app/temp && chown -R celeryuser:celeryuser /app/temp

# Change ownership of the entire /app directory to celeryuser
RUN chown -R celeryuser:celeryuser /app

# Set default environment variables
ENV FINAL_WIDTH=900
ENV FINAL_HEIGHT=1200
ENV ASPECT_RATIO_TOLERANCE=0.05

# Switch to the created user
USER celeryuser

# Command to run the bot
CMD ["python", "bot.py"]
