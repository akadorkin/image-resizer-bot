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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BACKEND_URL = os.getenv("CELERY_BACKEND_URL", "redis://redis:6379/0")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Проверка наличия BOT_TOKEN
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен в переменных окружения.")
    raise ValueError("BOT_TOKEN не установлен в переменных окружения.")

# Инициализация Celery
celery_app = Celery("tasks", broker=CELERY_BROKER_URL, backend=CELERY_BACKEND_URL)

# Telegram API URL
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Пути к директориям и файлам
STATS_DIR = "/app/stats"
STATS_FILE = os.path.join(STATS_DIR, "stats.json")

# Функции для загрузки и сохранения статистики
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

# Функция для отправки текстовых сообщений
def send_message(chat_id, text):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data)
        if not response.ok:
            logger.error(f"Не удалось отправить сообщение: {response.text}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")

# Функция для отправки документов
def send_document(chat_id, file_path, caption):
    url = f"{TELEGRAM_API_URL}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            response = requests.post(url, data=data, files=files)
            if not response.ok:
                logger.error(f"Не удалось отправить документ: {response.text}")
    except Exception as e:
        logger.error(f"Ошибка при отправке документа: {e}")

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
    archive_size = 0

    try:
        # Получение размера архива
        archive_size = os.path.getsize(archive_path)

        # Распаковка архива
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extracted_folder)
            logger.info(f"Архив {archive_path} успешно распакован как ZIP.")
        elif rarfile.is_rarfile(archive_path):
            with rarfile.RarFile(archive_path, "r") as rf:
                rf.extractall(extracted_folder)
            logger.info(f"Архив {archive_path} успешно распакован как RAR.")
        else:
            raise ValueError("Неподдерживаемый формат архива.")
        
        # Обработка файлов
        for root, _, files in os.walk(extracted_folder):
            for file_name in files:
                if file_name.startswith("._") or "__MACOSX" in root:
                    continue
                if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    image_path = os.path.join(root, file_name)
                    try:
                        with Image.open(image_path) as img:
                            width, height = img.size
                            aspect_ratio = width / height
                            logger.info(f"Обрабатывается изображение {image_path} с соотношением сторон {aspect_ratio:.2f}")

                            if not (1 - aspect_ratio_tolerance <= aspect_ratio <= 1 + aspect_ratio_tolerance):
                                logger.info(f"Изображение {image_path} не соответствует требуемому соотношению сторон.")
                                error_count +=1
                                continue

                            # Изменение размера изображения с сохранением пропорций и добавлением белого фона
                            new_img = ImageOps.pad(img, (final_width, final_height), color="white")
                            timestamp = int(time.time())
                            
                            # Разделение имени файла и расширения
                            name, ext = os.path.splitext(file_name)
                            resized_file_name = f"resized_{timestamp}_{name}{ext}"
                            
                            resized_file_path = os.path.join(processed_folder, resized_file_name)
                            new_img.save(resized_file_path, "JPEG", quality=100)
                            success_count +=1
                    except Exception as e:
                        logger.error(f"Ошибка при обработке изображения {image_path}: {e}")
                        error_count +=1

        # Создание нового архива с обработанными изображениями
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
            logger.info(f"Обработанные изображения архивированы в {processed_archive_path}")
        else:
            processed_archive_path = None

        # Обновление статистики
        stats["resizes"] += success_count

        if processed_archive_path and archive_size > 0:
            stats["top_archives"].append({
                "filename": os.path.basename(processed_archive_path),
                "size": archive_size,
                "time": round(time.time() - start_time, 2)  # Время выполнения в секундах с 2 знаками после запятой
            })
            # Сортировка топ-архивов по размеру
            stats["top_archives"] = sorted(stats["top_archives"], key=lambda x: x["size"], reverse=True)[:3]

        save_stats(stats)

        # Время выполнения
        end_time = time.time()
        elapsed_time = end_time - start_time

        status = {
            "success": success_count,
            "errors": error_count,
            "time": elapsed_time,
            "processed_archive": processed_archive_path,
            "archive_size": archive_size
        }

    except Exception as e:
        logger.error(f"Ошибка при обработке архива {archive_path}: {e}")
        status = {
            "success": 0,
            "errors": 0,
            "time": time.time() - start_time,
            "processed_archive": None,
            "archive_size": 0
        }

    finally:
        # Удаление временных папок и файлов
        if os.path.exists(extracted_folder):
            shutil.rmtree(extracted_folder)
        if os.path.exists(processed_folder):
            shutil.rmtree(processed_folder)
        if os.path.exists(archive_path):
            os.remove(archive_path)
        # processed_archive_path остаётся для бота

    return status

@celery_app.task
def process_images_task(user_id, image_paths, final_width, final_height, aspect_ratio_tolerance):
    stats = load_stats()

    for image_path in image_paths:
        path = Path(image_path)
        if not path.exists():
            logger.error(f"Изображение {image_path} не существует.")
            send_message(user_id, f"❌ Изображение не найдено: {path.name}")
            continue

        start_time = time.time()
        try:
            with Image.open(path) as img:
                width, height = img.size
                aspect_ratio = width / height
                logger.info(f"Обрабатывается изображение {image_path} с соотношением сторон {aspect_ratio:.2f}")

                if not (1 - aspect_ratio_tolerance <= aspect_ratio <= 1 + aspect_ratio_tolerance):
                    logger.info(f"Изображение {image_path} не соответствует требуемому соотношению сторон.")
                    send_message(
                        user_id,
                        f"❌ Изображение {path.name} не соответствует требуемому соотношению сторон."
                    )
                    continue

                # Изменение размера изображения с сохранением пропорций и добавлением белого фона
                new_img = ImageOps.pad(img, (final_width, final_height), color="white")
                timestamp = int(time.time())
                
                # Разделение имени файла и расширения
                name, ext = os.path.splitext(path.name)
                if not ext:
                    ext = '.jpg'  # Установка дефолтного расширения
                resized_file_name = f"resized_{timestamp}_{name}{ext}"
                resized_file_path = path.parent / resized_file_name
                new_img.save(resized_file_path, "JPEG", quality=100)

            # Время выполнения
            end_time = time.time()
            elapsed_time = end_time - start_time

            # Отправка обработанного изображения обратно пользователю с сообщением
            send_document(user_id, str(resized_file_path), f"✅ Изображение обработано: {resized_file_name}\n⏱️ Execution time: {elapsed_time:.2f} seconds")
            logger.info(f"Изображение {resized_file_path} отправлено пользователю {user_id}")

            # Обновление статистики
            stats["resizes"] += 1
            save_stats(stats)

            # Удаление обработанного изображения
            os.remove(resized_file_path)
            logger.info(f"Временное изображение {resized_file_path} удалено.")

        except Exception as e:
            logger.error(f"Ошибка при обработке изображения {image_path}: {e}")
            send_message(
                user_id,
                f"❌ Произошла ошибка при обработке изображения {path.name}."
            )

    # Удаление оригинальных изображений
    for image_path in image_paths:
        path = Path(image_path)
        if path.exists():
            path.unlink()
            logger.info(f"Оригинальное изображение {image_path} удалено.")
