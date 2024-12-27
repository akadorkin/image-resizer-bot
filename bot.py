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

from tasks import process_archive_task, process_images_task  # Импортируем задачи Celery

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ASPECT_RATIO_TOLERANCE = float(os.getenv("ASPECT_RATIO_TOLERANCE", 0.15))
FINAL_WIDTH = int(os.getenv("FINAL_WIDTH", 900))
FINAL_HEIGHT = int(os.getenv("FINAL_HEIGHT", 1200))

# Пути к директориям и файлам
TEMP_DIR = "/app/temp"
STATS_DIR = "/app/stats"
STATS_FILE = os.path.join(STATS_DIR, "stats.json")

# Создание необходимых директорий
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(STATS_DIR, exist_ok=True)

# Инициализация статистики
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

async def start(update: Update, context):
    instructions = (
        "<b>👋 Добро пожаловать!</b> Я бот для изменения размера изображений.\n\n"
        "📁 <b>Как пользоваться:</b>\n"
        "1️⃣ Отправьте архив <b>ZIP</b> или <b>RAR</b> с изображениями или несколькими изображениями/файлами.\n"
        "2️⃣ Отправьте отдельные изображения (JPG, PNG, WEBP, GIF).\n"
        "Я изменю размер изображений с соотношением сторон <b>1×1</b> до <b>3×4 (900×1200)</b> с белым фоном.\n"
        "✅ <b>Поддерживаемые форматы:</b> <b>JPG</b>, <b>PNG</b>, <b>WEBP</b>, <b>GIF</b>.\n"
        "❌ <b>Ignored:</b> Видео и скрытые файлы (начинающиеся с точки).\n"
        "📦 <b>Максимальный размер архива:</b> <b>20 МБ</b>.\n\n"
        "🔗 <b>Исходный код:</b> https://github.com/akadorkin/image-resizer-bot"
    )
    await update.message.reply_text(
        instructions, 
        parse_mode="HTML", 
        disable_web_page_preview=True
    )

async def handle_archive(update: Update, context):
    user_id = update.message.from_user.id
    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_stats(stats)
    stats["archives"] += 1
    save_stats(stats)

    file = update.message.document
    file_name = file.file_name.lower()

    # Проверка расширения файла
    if not (file_name.endswith('.zip') or file_name.endswith('.rar')):
        await update.message.reply_text("❌ Неподдерживаемый тип файла. Пожалуйста, отправьте архив ZIP или RAR.")
        return

    # Проверка размера файла
    if file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ Размер файла превышает лимит в 20 МБ.")
        return

    temp_folder = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(temp_folder, exist_ok=True)

    archive_path = os.path.join(temp_folder, file.file_name)

    try:
        telegram_file = await file.get_file()
        await telegram_file.download_to_drive(archive_path)
        logger.info(f"Скачан архив: {archive_path}")

        # Отправка сообщения о начале обработки архива
        await update.message.reply_text("📦 Архив взят в обработку...")

        # Отправка задачи Celery для обработки архива
        task = process_archive_task.delay(archive_path, FINAL_WIDTH, FINAL_HEIGHT, ASPECT_RATIO_TOLERANCE)
        logger.info(f"Запущена задача Celery: {task.id}")

        # Ожидание завершения задачи
        result = task.get(timeout=300)  # Таймаут 5 минут

        success = result.get("success", 0)
        errors = result.get("errors", 0)
        elapsed_time = result.get("time", 0)
        processed_archive_path = result.get("processed_archive", None)

        if processed_archive_path and os.path.exists(processed_archive_path):
            # Отправка обработанного архива
            await update.message.reply_document(
                document=open(processed_archive_path, "rb"),
                filename=os.path.basename(processed_archive_path),
                caption=(
                    f"✅ Processing complete.\n"
                    f"⏱️ Execution time: {elapsed_time:.2f} seconds"
                )
            )
            logger.info(f"Отправлен обработанный архив: {processed_archive_path}")
        else:
            await update.message.reply_text(
                f"❌ Обработка завершилась, но архив не был создан. Обработано изображений: {success}. Пропущено изображений: {errors}."
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке архива: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка при обработке архива: {e}")
    finally:
        # Очистка временной папки только в случае обработки архива
        if os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)
            logger.info(f"Временная папка {temp_folder} удалена.")

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
        # Извлекаем наивысшее разрешение
        if update.message.photo:
            images = [update.message.photo[-1]]  # Последний элемент - наивысшее разрешение
        elif update.message.document and update.message.document.mime_type.startswith('image/'):
            images = [update.message.document]
        else:
            images = []

        if not images:
            await update.message.reply_text("❌ Не удалось распознать изображения для обработки.")
            return  # Не вызываем cleanup здесь

        # Скачивание изображений
        image_paths = []
        for image in images:
            try:
                file = await image.get_file()
                # Используем оригинальное имя файла, если оно доступно
                if hasattr(image, 'file_name') and image.file_name:
                    file_name = image.file_name
                else:
                    # Для фото без имени файла генерируем уникальное имя
                    file_name = f"photo_{uuid.uuid4()}.jpg"
                file_path = os.path.join(temp_folder, file_name)
                await file.download_to_drive(file_path)
                logger.info(f"Скачано изображение: {file_path}")
                image_paths.append(file_path)
            except Exception as e:
                logger.error(f"Ошибка при скачивании изображения: {e}")
                await update.message.reply_text(f"❌ Ошибка при скачивании изображения: {e}")

        if not image_paths:
            await update.message.reply_text("❌ Нет изображений для обработки.")
            return  # Не вызываем cleanup здесь

        # Отправка задачи Celery для обработки изображений
        task = process_images_task.delay(user_id, image_paths, FINAL_WIDTH, FINAL_HEIGHT, ASPECT_RATIO_TOLERANCE)
        logger.info(f"Запущена задача Celery: {task.id}")

        # По вашему требованию, не отправляем сообщение о начале обработки

    except Exception as e:
        logger.error(f"Ошибка при обработке изображений: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка при обработке изображений: {e}")
    # Удаляем временную папку в Celery задаче

async def stats_command(update: Update, context):
    stats_message = (
        f"📊 Статистика бота:\n"
        f"👤 Уникальные пользователи: {len(stats['users'])}\n"
        f"📦 Обработано архивов: {stats['archives']}\n"
        f"🖼️ Обработано изображений: {stats['images']}\n"
        f"✂️ Изменено размеров изображений: {stats['resizes']}\n\n"
        f"🏆 Топ 3 самых больших архивов:\n"
    )

    if stats["top_archives"]:
        for i, archive in enumerate(stats["top_archives"], start=1):
            size_mb = archive["size"] / (1024 * 1024)
            time_seconds = archive["time"]
            stats_message += f"{i}. {archive['filename']} - {size_mb:.2f} МБ - ⏱️ {time_seconds:.2f} seconds\n"
    else:
        stats_message += "Нет данных."

    await update.message.reply_text(stats_message)

def main():
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд и сообщений
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

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
