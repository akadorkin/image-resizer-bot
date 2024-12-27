import os
import zipfile
import rarfile
from PIL import Image, ImageOps
from celery import Celery

# Celery configuration
broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
backend_url = os.getenv("CELERY_BACKEND_URL", "redis://redis:6379/0")
app = Celery("tasks", broker=broker_url, backend=backend_url)

# Constants
FINAL_WIDTH = int(os.getenv("FINAL_WIDTH", 900))
FINAL_HEIGHT = int(os.getenv("FINAL_HEIGHT", 1200))
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.15))

@app.task
def process_archive(archive_path, temp_folder, processed_folder):
    extracted_folder = os.path.join(temp_folder, "extracted")
    os.makedirs(extracted_folder, exist_ok=True)

    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extracted_folder)
        elif rarfile.is_rarfile(archive_path):
            with rarfile.RarFile(archive_path, "r") as rf:
                rf.extractall(extracted_folder)
        else:
            return {"success": 0, "errors": 0, "archive": None}
    except Exception:
        return {"success": 0, "errors": 0, "archive": None}

    success_count = 0
    error_count = 0

    for root, _, files in os.walk(extracted_folder):
        for file_name in files:
            if file_name.startswith('.') or not file_name.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                continue
            try:
                file_path = os.path.join(root, file_name)
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

    if success_count == 0:
        return {"success": 0, "errors": error_count, "archive": None}

    result_archive_path = os.path.join(temp_folder, f"processed_{os.path.basename(temp_folder)}.zip")
    with zipfile.ZipFile(result_archive_path, "w") as zf:
        for root, _, files in os.walk(processed_folder):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                zf.write(file_path, os.path.relpath(file_path, processed_folder))

    return {"success": success_count, "errors": error_count, "archive": result_archive_path}
