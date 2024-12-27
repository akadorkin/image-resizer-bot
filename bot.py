import os
import zipfile
import rarfile
from PIL import Image, ImageOps
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import uuid
from dotenv import load_dotenv
from celery import Celery

from tasks import process_archive

TEMP_DIR = "./temp"
os.makedirs(TEMP_DIR, exist_ok=True)

if not os.access(TEMP_DIR, os.W_OK):
    raise PermissionError(f"Cannot write to temporary directory: {TEMP_DIR}")

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.15))
FINAL_WIDTH = int(os.getenv("FINAL_WIDTH", 900))
FINAL_HEIGHT = int(os.getenv("FINAL_HEIGHT", 1200))

# Celery configuration
celery_app = Celery("tasks", broker="redis://redis:6379/0", backend="redis://redis:6379/0")

# Temporary directory for files
TEMP_DIR = "./temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Bot statistics
stats = {"users": set(), "archives": 0, "images": 0, "resizes": 0}

async def start(update: Update, context):
    instructions = (
        "<b>👋 Welcome!</b> I am a bot for processing images.\n\n"
        "📁 <b>How to use:</b> Upload a <b>ZIP</b> or <b>RAR</b> archive containing images.\n"
        "🖼️ I will resize <b>1×1 images</b> to <b>3×4 format (900×1200)</b> with a white background.\n"
        "✅ <b>Supported formats:</b> <b>JPG</b>, <b>PNG</b>, <b>WEBP</b>, <b>GIF</b>.\n"
        "❌ <b>Ignored:</b> Videos and hidden files (starting with a dot).\n"
        "📦 <b>Maximum archive size:</b> <b>20 MB</b>.\n\n"
        "🔗 <b>Source code available on GitHub:</b> https://github.com/akadorkin/image-resizer-bot"
    )
    reply_markup = ReplyKeyboardMarkup([["📦Send Archive"]], resize_keyboard=True)
    await update.message.reply_text(instructions, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)


async def handle_archive(update: Update, context):
    user_id = update.message.from_user.id
    stats["users"].add(user_id)
    stats["archives"] += 1

    file = update.message.document
    if file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File size exceeds the 20 MB limit.")
        return

    temp_folder = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(temp_folder, exist_ok=True)

    archive_path = os.path.join(temp_folder, file.file_name)
    processed_folder = os.path.join(temp_folder, "processed")
    os.makedirs(processed_folder, exist_ok=True)

    telegram_file = await file.get_file()
    await telegram_file.download_to_drive(archive_path)

    await update.message.reply_text("📦 Archive received. Processing...")

    # Process the archive asynchronously using Celery
    result = process_archive.apply_async((archive_path, temp_folder, processed_folder))
    result_output = result.get(timeout=60)

    if not result_output["success"]:
        await update.message.reply_text("❌ No valid images found in the archive.")
    else:
        processed_archive = result_output["archive"]
        await update.message.reply_document(
            document=open(processed_archive, "rb"),
            caption=(
                f"✅ Processing complete.\n"
                f"Resized images: {result_output['success']}\n"
                f"Skipped images: {result_output['errors']}."
            )
        )

    # Cleanup
    for root, dirs, files in os.walk(temp_folder, topdown=False):
        for file in files:
            os.remove(os.path.join(root, file))
        for dir in dirs:
            os.rmdir(os.path.join(root, dir))
    os.rmdir(temp_folder)

async def stats_command(update: Update, context):
    stats_message = (
        f"📊 Bot statistics:\n"
        f"👤 Unique users: {len(stats['users'])}\n"
        f"📦 Archives processed: {stats['archives']}\n"
        f"🖼️ Images processed: {stats['images']}\n"
        f"✂️ Images resized: {stats['resizes']}"
    )
    await update.message.reply_text(stats_message)

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_archive))
    application.add_handler(CommandHandler("stats", stats_command))

    application.run_polling()



if __name__ == "__main__":
    main()
