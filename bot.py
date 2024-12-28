import os
import zipfile
import rarfile
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import uuid
from dotenv import load_dotenv
import shutil
import logging

from tasks import process_archive_task, process_images_task  # Import Celery tasks

# **Logging Configuration**
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# **Load Environment Variables**
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.15))
FINAL_WIDTH = int(os.getenv("FINAL_WIDTH", 900))
FINAL_HEIGHT = int(os.getenv("FINAL_HEIGHT", 1200))

# **Directories Setup**
TEMP_DIR = "/app/temp"
STATS_DIR = "/app/stats"
STATS_FILE = os.path.join(STATS_DIR, "stats.json")

# **Ensure Directories Exist**
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(STATS_DIR, exist_ok=True)

# **Initialize Statistics**
def load_stats():
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
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=4)

stats = load_stats()

# **Start Command Handler**
async def start(update: Update, context):
    instructions = (
        "<b>👋 Welcome!</b> I am an image resizing bot.\n\n"
        "📁 <b>How to Use:</b>\n"
        "1️⃣ Send a <b>ZIP</b> or <b>RAR</b> archive containing images.\n"
        "2️⃣ Send individual images as <b>documents</b> (JPG, PNG, WEBP, GIF).\n"
        "I will resize the images from <b>1×1</b> to <b>3×4 (900×1200)</b> with a white background.\n"
        "✅ <b>Supported Formats:</b> <b>JPG</b>, <b>PNG</b>, <b>WEBP</b>.\n"
        "❌ <b>Ignored:</b> Videos and hidden files (starting with a dot).\n"
        "📦 <b>Maximum Archive Size:</b> <b>20 MB</b>.\n\n"
        "🔗 <b>Source Code:</b> https://github.com/akadorkin/image-resizer-bot"
    )
    await update.message.reply_text(
        instructions, 
        parse_mode="HTML", 
        disable_web_page_preview=True
    )

# **Archive Handling**
async def handle_archive(update: Update, context):
    user_id = update.message.from_user.id
    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_stats(stats)
    stats["archives"] += 1
    save_stats(stats)

    file = update.message.document
    file_name = file.file_name.lower()

    # **Check File Extension**
    if not (file_name.endswith('.zip') or file_name.endswith('.rar')):
        await update.message.reply_text("❌ Unsupported file type. Please send a ZIP or RAR archive.")
        return

    # **Check File Size**
    if file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File size exceeds the 20 MB limit.")
        return

    temp_folder = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(temp_folder, exist_ok=True)

    archive_path = os.path.join(temp_folder, file.file_name)

    try:
        telegram_file = await file.get_file()
        await telegram_file.download_to_drive(archive_path)
        logger.info(f"Downloaded archive: {archive_path}")

        # **Notify User Processing Started**
        await update.message.reply_text("📦 Archive received for processing...")

        # **Trigger Celery Task**
        task = process_archive_task.delay(archive_path, FINAL_WIDTH, FINAL_HEIGHT, ASPECT_RATIO_TOLERANCE)
        logger.info(f"Celery task started: {task.id}")

        # **Wait for Task Completion**
        result = task.get(timeout=300)  # Timeout after 5 minutes

        success = result.get("success", 0)
        errors = result.get("errors", 0)
        elapsed_time = result.get("time", 0)
        processed_archive_path = result.get("processed_archive", None)

        if processed_archive_path and os.path.exists(processed_archive_path):
            # **Send Processed Archive Back to User**
            await update.message.reply_document(
                document=open(processed_archive_path, "rb"),
                filename=os.path.basename(processed_archive_path),
                caption=(
                    f"✅ <b>Processing Complete.</b>\n"
                    f"⏱️ <b>Execution Time:</b> {elapsed_time:.2f} seconds"
                ),
                parse_mode="HTML"
            )
            logger.info(f"Sent processed archive: {processed_archive_path}")
        else:
            await update.message.reply_text(
                f"❌ Processing completed, but the archive was not created. Images processed: {success}. Images skipped: {errors}."
            )
    except Exception as e:
        logger.error(f"Error processing archive: {e}")
        await update.message.reply_text(f"❌ An error occurred while processing the archive: {e}")
    finally:
        # **Clean Up Temporary Folder**
        if os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)
            logger.info(f"Temporary folder {temp_folder} deleted.")

# **Image Handling**
async def handle_images(update: Update, context):
    user_id = update.message.from_user.id
    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_stats(stats)
    stats["images"] += 1
    save_stats(stats)

    temp_folder = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(temp_folder, exist_ok=True)

    try:
        # **Determine Image Type**
        if update.message.photo:
            images = [update.message.photo[-1]]  # Highest resolution
        elif update.message.document and update.message.document.mime_type.startswith('image/'):
            images = [update.message.document]
        else:
            images = []

        if not images:
            await update.message.reply_text("❌ No recognizable images found for processing.")
            return

        # **Download Images**
        image_paths = []
        for image in images:
            try:
                file = await image.get_file()
                # **Use Original Filename if Available**
                if hasattr(image, 'file_name') and image.file_name:
                    file_name = image.file_name
                else:
                    # **Generate Unique Name for Photos without Filename**
                    file_name = f"photo_{uuid.uuid4()}.jpg"
                file_path = os.path.join(temp_folder, file_name)
                await file.download_to_drive(file_path)
                logger.info(f"Downloaded image: {file_path}")
                image_paths.append(file_path)
            except Exception as e:
                logger.error(f"Error downloading image: {e}")
                await update.message.reply_text(f"❌ Error downloading image: {e}")

        if not image_paths:
            await update.message.reply_text("❌ No images available for processing.")
            return

        # **Trigger Celery Task for Images**
        task = process_images_task.delay(user_id, image_paths, FINAL_WIDTH, FINAL_HEIGHT, ASPECT_RATIO_TOLERANCE)
        logger.info(f"Celery task started: {task.id}")

        # **No Immediate Notification Required**
        # Processing is handled asynchronously; responses are sent after processing
    except Exception as e:
        logger.error(f"Error handling images: {e}")
        await update.message.reply_text(f"❌ An error occurred while handling images: {e}")
    # **Temporary Folder Cleanup is Handled in Celery Task**

# **Statistics Command Handler**
async def stats_command(update: Update, context):
    stats_message = (
        f"📊 <b>Bot Statistics:</b>\n"
        f"👤 <b>Unique Users:</b> {len(stats['users'])}\n"
        f"📦 <b>Archives Processed:</b> {stats['archives']}\n"
        f"🖼️ <b>Images Processed:</b> {stats['images']}\n"
        f"✂️ <b>Images Resized:</b> {stats['resizes']}\n\n"
        f"🏆 <b>Top 3 Largest Archives:</b>\n"
    )

    if stats["top_archives"]:
        for i, archive in enumerate(stats["top_archives"], start=1):
            size_mb = archive["size"] / (1024 * 1024)
            time_seconds = archive["time"]
            stats_message += f"{i}. {archive['filename']} - {size_mb:.2f} MB - ⏱️ {time_seconds:.2f} seconds\n"
    else:
        stats_message += "No data available."

    await update.message.reply_text(stats_message, parse_mode="HTML")

# **Main Function to Run the Bot**
def main():
    application = Application.builder().token(TOKEN).build()

    # **Add Handlers for Commands and Messages**
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.Document.MimeType("application/zip") | filters.Document.MimeType("application/x-rar-compressed"),
        handle_archive
    ))
    application.add_handler(MessageHandler(filters.PHOTO, handle_images))
    application.add_handler(MessageHandler(
        filters.Document.MimeType("image/jpeg") |
        filters.Document.MimeType("image/png") |
        filters.Document.MimeType("image/webp") |
        filters.Document.MimeType("image/gif"),
        handle_images
    ))
    application.add_handler(CommandHandler("stats", stats_command))

    # **Start the Bot**
    application.run_polling()

if __name__ == "__main__":
    main()
