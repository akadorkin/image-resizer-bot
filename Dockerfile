# Use the official Python 3.9 slim image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot's source code
COPY . .

# Set environment variables (example, should be overridden at runtime)
ENV FINAL_WIDTH=900
ENV FINAL_HEIGHT=1200
ENV ASPECT_RATIO_TOLERANCE=0.05

# Command to run the bot
CMD ["python", "bot.py"]
