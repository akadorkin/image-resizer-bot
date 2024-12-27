import os
import zipfile
import rarfile
from PIL import Image, ImageOps
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
FINAL_WIDTH = int(os.getenv("FINAL_WIDTH", 900))
FINAL_HEIGHT = int(os.getenv("FINAL_HEIGHT", 1200))
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.05))

# Temporary folder for processing
TEMP_DIR = "./temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Statistics dictionary
stats = {"users": set(), "archives": 0, "images": 0, "resizes": 0}

async def start(update: Update, context: CallbackContext):
    instructions = (
        "👋 Hi! I'm an image processing bot.\n"
        "📁 Please upload a ZIP or RAR archive containing square-like images.\n"
        "🖼️ I'll resize them to 3:4 aspect ratio (default 900×1200) and add a white background.\n"
        "📦 Maximum archive size: 20 MB.\n"
        "🔗 Source code: https://github.com/akadorkin/image-resizer-bot"
    )
    reply_markup = ReplyKeyboardMarkup([["Upload Archive"]], resize_keyboard=True)
    await update.message.reply_text(instructions, reply_markup=reply_markup, disable_web_page_preview=True)

async def handle_archive(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    stats["users"].add(user_id)
    stats["archives"] += 1

    file = update.message.document
    if file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File exceeds the maximum size of 20 MB.")
        return

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

    def is_approximately_square(width, height, tolerance):
        return abs(width - height) / max(width, height) <= tolerance

    for root, _, files in os.walk(extracted_folder):
        for file_name in files:
            try:
                file_path = os.path.join(root, file_name)
                with Image.open(file_path) as img:
                    if not is_approximately_square(img.size[0], img.size[1], ASPECT_RATIO_TOLERANCE):
                        error_count += 1
                        continue

                    stats["images"] += 1

                    new_img = ImageOps.pad(img, (FINAL_WIDTH, FINAL_HEIGHT), color="white")

                    new_file_name = f"resized_{os.path.splitext(file_name)[0]}.jpg"
                    new_file_path = os.path.join(processed_folder, new_file_name)
                    new_img.save(new_file_path, "JPEG", quality=100)
                    stats["resizes"] += 1
                    success_count += 1
            except Exception:
                error_count += 1

    if success_count == 0:
        await update.message.reply_text("❌ No suitable images found in the archive.")
    else:
        result_archive_path = os.path.join(temp_folder, "result.zip")
        with zipfile.ZipFile(result_archive_path, "w") as zf:
            for root, _, files in os.walk(processed_folder):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    zf.write(file_path, os.path.relpath(file_path, processed_folder))

        await update.message.reply_document(
            document=open(result_archive_path, "rb"),
            caption=f"✅ Done! Processed: {success_count} files. Failed: {error_count}.",
        )

    for root, dirs, files in os.walk(temp_folder, topdown=False):
        for file in files:
            os.remove(os.path.join(root, file))
        for dir in dirs:
            os.rmdir(os.path.join(root, dir))
    os.rmdir(temp_folder)

async def stats_command(update: Update, context: CallbackContext):
    stats_message = (
        f"📊 Bot Statistics:\n"
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
