import os
import zipfile
import rarfile
import uuid
from datetime import datetime
from PIL import Image, ImageOps
from celery import Celery

# Celery configuration
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
app = Celery("tasks", broker=broker_url)

# Constants
TEMP_DIR = "./temp"
FINAL_WIDTH = int(os.getenv("FINAL_WIDTH", 900))
FINAL_HEIGHT = int(os.getenv("FINAL_HEIGHT", 1200))
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.15))

@app.task
def process_archive(archive_path, extracted_folder, processed_folder):
    success_count = 0
    error_count = 0

    for root, _, files in os.walk(extracted_folder):
        for file_name in files:
            try:
                file_path = os.path.join(root, file_name)
                if file_name.startswith(".") or not file_name.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    continue

                with Image.open(file_path) as img:
                    width, height = img.size
                    aspect_ratio = width / height
                    if not (1 - ASPECT_RATIO_TOLERANCE <= aspect_ratio <= 1 + ASPECT_RATIO_TOLERANCE):
                        error_count += 1
                        continue

                    # Create resized image with white background
                    new_img = ImageOps.pad(img, (FINAL_WIDTH, FINAL_HEIGHT), color="white")
                    new_file_name = f"_resized_{os.path.splitext(file_name)[0]}.jpg"
                    new_file_path = os.path.join(processed_folder, new_file_name)
                    new_img.save(new_file_path, "JPEG", quality=100)
                    success_count += 1
            except Exception:
                error_count += 1

    return {"success": success_count, "errors": error_count}
