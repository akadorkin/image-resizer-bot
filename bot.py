import os
import zipfile
import rarfile
import uuid
from datetime import datetime
from PIL import Image, ImageOps
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
from dotenv import load_dotenv
from tasks import process_archive

# Load environment variables
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in the environment or .env file.")

# Temporary folder for processing
TEMP_DIR = "./temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Stats dictionary
stats = {"users": set(), "archives": 0, "images": 0, "resizes": 0}

async def start(update: Update, context: CallbackContext):
    instructions = (
        "👋 <b>Welcome!</b> I am a bot for processing images.\n"
        "📁 <b>How to use:</b> Upload a ZIP or RAR archive containing images.\n"
        "🖼️ I will resize them to 3×4 format (900×1200) with a white background.\n"
        "✅ <b>Supported formats:</b> JPG, PNG, WEBP, GIF.\n"
        "❌ <b>Ignored:</b> Videos and hidden files (starting with a dot).\n"
        "📦 <b>Maximum archive size:</b> 20 MB.\n"
        "🔗 <b>Source code available on GitHub: https://github.com/akadorkin/image-resizer-bot</b>"
    )
    reply_markup = ReplyKeyboardMarkup([["Upload Archive"]], resize_keyboard=True)
    await update.message.reply_text(
        instructions, reply_markup=reply_markup, disable_web_page_preview=True, parse_mode="HTML"
    )

async def handle_archive(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    stats["users"].add(user_id)
    stats["archives"] += 1

    file = update.message.document
    if file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File size exceeds the 20 MB limit.")
        return

    await update.message.reply_text(f"📂 Archive received: <b>{file.file_name}</b>. Processing started...", parse_mode="HTML")

    temp_folder = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(temp_folder, exist_ok=True)

    archive_path = os.path.join(temp_folder, file.file_name)
    telegram_file = await file.get_file()
    await telegram_file.download_to_drive(archive_path)

    extracted_folder = os.path.join(temp_folder, "extracted")
    processed_folder = os.path.join(temp_folder, "processed")
    os.makedirs(extracted_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)

    # Extract archive
    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extracted_folder)
        elif rarfile.is_rarfile(archive_path):
            with rarfile.RarFile(archive_path, "r") as rf:
                rf.extractall(extracted_folder)
        else:
            await update.message.reply_text("⚠️ Unsupported archive format.")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Error during extraction: {e}")
        return

    # Send task to Celery
    task = process_archive.delay(archive_path, extracted_folder, processed_folder)

    await update.message.reply_text(f"Your archive is being processed. Task ID: {task.id}")

    # Wait for result
    try:
        result = task.get(timeout=300)
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        result_archive_name = f"processed_{current_date}_{file.file_name}"
        result_archive_path = os.path.join(temp_folder, result_archive_name)
        
        with zipfile.ZipFile(result_archive_path, "w") as zf:
            for root, _, files in os.walk(processed_folder):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    zf.write(file_path, os.path.relpath(file_path, processed_folder))

        await update.message.reply_document(
            document=open(result_archive_path, "rb"),
            caption=(
                f"✅ Archive <b>{result_archive_name}</b> is ready!\n"
                f"✔️ Processed images: {result['success']}\n"
                f"❌ Skipped images: {result['errors']}"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error during processing: {e}")

    # Cleanup
    for root, dirs, files in os.walk(temp_folder, topdown=False):
        for file in files:
            os.remove(os.path.join(root, file))
        for dir in dirs:
            os.rmdir(os.path.join(root, dir))
    os.rmdir(temp_folder)

async def stats_command(update: Update, context: CallbackContext):
    stats_message = (
        f"📊 Bot statistics:\n"
        f"👤 Unique users: {len(stats['users'])}\n"
        f"📦 Processed archives: {stats['archives']}\n"
        f"🖼️ Processed images: {stats['images']}\n"
        f"✂️ Resized images: {stats['resizes']}"
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