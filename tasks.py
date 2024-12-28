import os
from pathlib import Path
from PIL import Image, ImageOps
from celery import Celery
import logging
import zipfile
import rarfile
import time
import shutil
import requests
import json
from filelock import FileLock

# **Logging Configuration**
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# **Load Environment Variables**
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BACKEND_URL = os.getenv("CELERY_BACKEND_URL", "redis://redis:6379/0")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# **Check for BOT_TOKEN**
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set in environment variables.")
    raise ValueError("BOT_TOKEN not set in environment variables.")

# **Initialize Celery**
celery_app = Celery("tasks", broker=CELERY_BROKER_URL, backend=CELERY_BACKEND_URL)

# **Telegram API URL**
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# **Directories and Files Paths**
STATS_DIR = "/app/stats"
STATS_FILE = os.path.join(STATS_DIR, "stats.json")
STATS_LOCK_FILE = STATS_FILE + ".lock"

# **Statistics Management with File Locking**
def load_stats():
    lock = FileLock(STATS_LOCK_FILE)
    with lock:
        if not os.path.exists(STATS_FILE):
            stats = {
                "users": [],
                "archives": 0,
                "images": 0,
                "resizes": 0,
                "top_archives": []
            }
            save_stats(stats)
        else:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                stats = json.load(f)
    return stats

def save_stats(stats):
    lock = FileLock(STATS_LOCK_FILE)
    with lock:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)

# **Function to Send Messages**
def send_message(chat_id, text):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data)
        if not response.ok:
            logger.error(f"Failed to send message: {response.text}")
    except Exception as e:
        logger.error(f"Error sending message: {e}")

# **Function to Send Documents**
def send_document(chat_id, file_path, caption):
    url = f"{TELEGRAM_API_URL}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            response = requests.post(url, data=data, files=files)
            if not response.ok:
                logger.error(f"Failed to send document: {response.text}")
    except Exception as e:
        logger.error(f"Error sending document: {e}")

# **Celery Task to Process Archives**
@celery_app.task
def process_archive_task(archive_path, final_width, final_height, aspect_ratio_tolerance):
    stats = load_stats()
    start_time = time.time()
    extracted_folder = os.path.join(os.path.dirname(archive_path), "extracted")
    processed_folder = os.path.join(os.path.dirname(archive_path), "processed")
    os.makedirs(extracted_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)

    success_count = 0
    error_count = 0
    total_images_in_archive = 0
    archive_size = 0

    try:
        # **Get Archive Size**
        archive_size = os.path.getsize(archive_path)
        logger.info(f"Archive size {archive_path}: {archive_size} bytes")

        # **Extract Archive**
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extracted_folder)
            logger.info(f"Archive {archive_path} extracted as ZIP.")
        elif rarfile.is_rarfile(archive_path):
            with rarfile.RarFile(archive_path, "r") as rf:
                rf.extractall(extracted_folder)
            logger.info(f"Archive {archive_path} extracted as RAR.")
        else:
            raise ValueError("Unsupported archive format.")

        # **Process Images**
        for root, _, files in os.walk(extracted_folder):
            for file_name in files:
                if file_name.startswith("._") or "__MACOSX" in root:
                    logger.info(f"Ignoring file {file_name} in folder {root}")
                    continue
                if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    total_images_in_archive += 1  # **Count as Image Processed**
                    image_path = os.path.join(root, file_name)
                    try:
                        with Image.open(image_path) as img:
                            width, height = img.size
                            aspect_ratio = width / height
                            logger.info(f"Processing image {image_path} with aspect ratio {aspect_ratio:.2f}")

                            if not (1 - aspect_ratio_tolerance <= aspect_ratio <= 1 + aspect_ratio_tolerance):
                                logger.info(f"Image {image_path} does not meet the required aspect ratio.")
                                error_count += 1
                                continue

                            # **Resize Image with White Background**
                            new_img = ImageOps.pad(img, (final_width, final_height), color="white")
                            timestamp = int(time.time())

                            # **Preserve Original Filename with Prefix**
                            name, ext = os.path.splitext(file_name)
                            resized_file_name = f"resized_{timestamp}_{name}{ext}"
                            resized_file_path = os.path.join(processed_folder, resized_file_name)
                            new_img.save(resized_file_path, "JPEG", quality=100)
                            logger.info(f"Saved resized image: {resized_file_path}")
                            success_count += 1
                    except Exception as e:
                        logger.error(f"Error processing image {image_path}: {e}")
                        error_count += 1

        # **Create New Archive with Resized Images**
        if success_count > 0:
            timestamp = int(time.time())
            original_archive_name = os.path.basename(archive_path)
            resized_archive_name = f"resized_{timestamp}_{original_archive_name}"
            processed_archive_path = os.path.join(os.path.dirname(archive_path), resized_archive_name)
            with zipfile.ZipFile(processed_archive_path, "w") as zf:
                for root, _, files in os.walk(processed_folder):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        zf.write(file_path, arcname=file_name)
            logger.info(f"Resized images archived in {processed_archive_path}")
        else:
            processed_archive_path = None
            logger.info(f"No resized images created for archive {archive_path}")

        # **Update Statistics**
        stats["images"] += total_images_in_archive  # **Total Images Processed**
        stats["resizes"] += success_count  # **Images Resized**

        if processed_archive_path and archive_size > 0:
            stats["top_archives"].append({
                "filename": os.path.basename(processed_archive_path),
                "size": archive_size,
                "time": round(time.time() - start_time, 2)  # Execution time in seconds
            })
            # **Sort Top Archives by Size Descending**
            stats["top_archives"] = sorted(stats["top_archives"], key=lambda x: x["size"], reverse=True)[:3]

        save_stats(stats)

        # **Execution Time**
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"Archive processing time: {elapsed_time:.2f} seconds")

        status = {
            "success": success_count,
            "errors": error_count,
            "time": elapsed_time,
            "processed_archive": processed_archive_path,
            "archive_size": archive_size
        }

    except Exception as e:
        logger.error(f"Error processing archive {archive_path}: {e}")
        status = {
            "success": 0,
            "errors": 0,
            "time": time.time() - start_time,
            "processed_archive": None,
            "archive_size": 0
        }

    finally:
        # **Clean Up Temporary Files and Folders**
        if os.path.exists(extracted_folder):
            shutil.rmtree(extracted_folder)
            logger.info(f"Temporary folder {extracted_folder} deleted.")
        if os.path.exists(processed_folder):
            shutil.rmtree(processed_folder)
            logger.info(f"Temporary folder {processed_folder} deleted.")
        if os.path.exists(archive_path):
            os.remove(archive_path)
            logger.info(f"Original archive {archive_path} deleted.")

    return status

# **Celery Task to Process Individual Images**
@celery_app.task
def process_images_task(user_id, image_paths, final_width, final_height, aspect_ratio_tolerance):
    stats = load_stats()

    for image_path in image_paths:
        path = Path(image_path)
        if not path.exists():
            logger.error(f"Image {image_path} does not exist.")
            send_message(user_id, f"❌ Image not found: {path.name}")
            continue

        start_time = time.time()
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                aspect_ratio = width / height
                logger.info(f"Processing image {image_path} with aspect ratio {aspect_ratio:.2f}")

                # **Count as Image Processed**
                stats["images"] += 1

                if not (1 - aspect_ratio_tolerance <= aspect_ratio <= 1 + aspect_ratio_tolerance):
                    logger.info(f"Image {image_path} does not meet the required aspect ratio.")
                    send_message(
                        user_id,
                        f"❌ Image {path.name} does not meet the required aspect ratio."
                    )
                    continue

                # **Resize Image with White Background**
                new_img = ImageOps.pad(img, (final_width, final_height), color="white")
                timestamp = int(time.time())

                # **Preserve Original Filename with Prefix**
                name, ext = os.path.splitext(path.name)
                if not ext:
                    ext = '.jpg'  # Set default extension if missing
                resized_file_name = f"resized_{timestamp}_{name}{ext}"
                resized_file_path = path.parent / resized_file_name
                new_img.save(resized_file_path, "JPEG", quality=100)
                logger.info(f"Saved resized image: {resized_file_path}")

            # **Execution Time**
            end_time = time.time()
            elapsed_time = end_time - start_time
            logger.info(f"Image processing time: {elapsed_time:.2f} seconds")

            # **Send Resized Image Back to User**
            send_document(user_id, str(resized_file_path), f"✅ Image processed: {resized_file_name}\n⏱️ Execution time: {elapsed_time:.2f} seconds")
            logger.info(f"Sent resized image {resized_file_path} to user {user_id}")

            # **Update Statistics**
            stats["resizes"] += 1
            save_stats(stats)

            # **Delete Resized Image from Server**
            os.remove(resized_file_path)
            logger.info(f"Temporary resized image {resized_file_path} deleted.")

        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            send_message(
                user_id,
                f"❌ An error occurred while processing image {path.name}."
            )

    # **Delete Original Images from Server**
    for image_path in image_paths:
        path = Path(image_path)
        if path.exists():
            path.unlink()
            logger.info(f"Original image {image_path} deleted.")
