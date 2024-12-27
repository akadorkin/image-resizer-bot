import os
import zipfile
import rarfile
import uuid
from datetime import datetime
from PIL import Image, ImageOps
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
from tasks import process_archive

# Load environment variables from .env file
load_dotenv()

# Retrieve the bot token from environment variables
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in the environment or .env file.")

# Define the temporary directory for processing files
TEMP_DIR = "./temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize statistics
stats = {
    "users": set(),
    "archives": 0,
    "images": 0,
    "resizes": 0,
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for the /start command. Sends welcome instructions to the user.
    """
    instructions = (
        "👋 <b>Welcome!</b> I am a bot for processing images.\n\n"
        "📁 <b>How to use:</b> Upload a ZIP or RAR archive containing images.\n"
        "🖼️ I will resize them to a 3×4 format (900×1200) with a white background.\n"
        "✅ <b>Supported formats:</b> JPG, PNG, WEBP, GIF.\n"
        "❌ <b>Ignored:</b> Videos and hidden files (starting with a dot).\n"
        "📦 <b>Maximum archive size:</b> 20 MB.\n\n"
        "🔗 Source code available on GitHub: https://github.com/akadorkin/image-resizer-bot"
    )
    reply_markup = ReplyKeyboardMarkup(
        [["Upload Archive"]], resize_keyboard=True, one_time_keyboard=False
    )
    await update.message.reply_text(
        instructions,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        parse_mode="HTML",
    )


async def handle_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for processing uploaded archive files (ZIP or RAR).
    """
    user = update.effective_user
    user_id = user.id
    stats["users"].add(user_id)
    stats["archives"] += 1

    file = update.message.document
    if not file:
        await update.message.reply_text("❌ Please upload a valid ZIP or RAR archive.")
        return

    # Check file size (limit: 20 MB)
    if file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File size exceeds the 20 MB limit.")
        return

    # Acknowledge receipt of the archive
    await update.message.reply_text(
        f"📂 Archive received: <b>{file.file_name}</b>. Processing started...",
        parse_mode="HTML",
    )

    # Create unique temporary directories
    unique_id = str(uuid.uuid4())
    temp_folder = os.path.join(TEMP_DIR, unique_id)
    extracted_folder = os.path.join(temp_folder, "extracted")
    processed_folder = os.path.join(temp_folder, "processed")
    os.makedirs(extracted_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)

    archive_path = os.path.join(temp_folder, file.file_name)

    try:
        # Download the archive from Telegram
        telegram_file = await file.get_file()
        await telegram_file.download_to_drive(archive_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to download the archive: {e}")
        return

    # Extract the archive
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

    await update.message.reply_text(
        f"🔄 Your archive is being processed. Task ID: {task.id}"
    )

    # Wait for the task to complete without blocking the event loop
    try:
        # Use run_in_executor to avoid blocking
        loop = context.application.loop
        result = await loop.run_in_executor(None, task.get, 300)

        success = result.get("success", 0)
        errors = result.get("errors", 0)
        stats["images"] += success + errors
        stats["resizes"] += success

        # Create the result archive
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        result_archive_name = f"processed_{current_date}_{file.file_name}"
        result_archive_path = os.path.join(temp_folder, result_archive_name)

        with zipfile.ZipFile(result_archive_path, "w") as zf:
            for root, _, files in os.walk(processed_folder):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    zf.write(
                        file_path,
                        os.path.relpath(file_path, processed_folder),
                    )

        # Send the processed archive back to the user
        await update.message.reply_document(
            document=InputFile(result_archive_path),
            caption=(
                f"✅ Archive <b>{result_archive_name}</b> is ready!\n"
                f"✔️ Processed images: {success}\n"
                f"❌ Skipped images: {errors}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error during processing: {e}")
    finally:
        # Cleanup temporary files
        try:
            for root, dirs, files in os.walk(temp_folder, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(temp_folder)
        except Exception as e:
            # Log the cleanup error (you can enhance this with proper logging)
            print(f"🔧 Cleanup error: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for the /stats command. Sends bot usage statistics to the user.
    """
    stats_message = (
        f"📊 <b>Bot Statistics:</b>\n"
        f"👤 Unique users: {len(stats['users'])}\n"
        f"📦 Processed archives: {stats['archives']}\n"
        f"🖼️ Processed images: {stats['images']}\n"
        f"✂️ Resized images: {stats['resizes']}"
    )
    await update.message.reply_text(stats_message, parse_mode="HTML")


def main():
    """
    Main function to start the Telegram bot.
    """
    application = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_archive))
    application.add_handler(CommandHandler("stats", stats_command))

    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()
