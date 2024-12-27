import os
import zipfile
import rarfile
import uuid
from datetime import datetime
from PIL import Image, ImageOps
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.15))  # Aspect ratio tolerance from .env

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
        "🔗 <b>Source code available on GitHub:</b> <a href='https://github.com/akadorkin/image-resizer-bot'>Image Resizer Bot</a>"
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
    os.makedirs(extracted_folder, exist_ok=True)

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

    processed_folder = os.path.join(temp_folder, "processed")
    os.makedirs(processed_folder, exist_ok=True)

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

                    stats["images"] += 1

                    # Create image with a white background
                    new_width = 900
                    new_height = 1200
                    new_img = ImageOps.pad(img, (new_width, new_height), color="white")

                    new_file_name = f"_resized_{os.path.splitext(file_name)[0]}.jpg"
                    new_file_path = os.path.join(processed_folder, new_file_name)
                    new_img.save(new_file_path, "JPEG", quality=100)
                    stats["resizes"] += 1
                    success_count += 1
            except Exception:
                error_count += 1

    if success_count == 0:
        await update.message.reply_text("❌ No suitable images found in the archive.")
    else:
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
                f"✔️ Processed images: {success_count}\n"
                f"❌ Skipped images: {error_count}"
            ),
            parse_mode="HTML"
        )

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
