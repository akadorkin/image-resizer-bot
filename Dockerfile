# Используем официальный Python 3.9 slim образ
FROM python:3.9-slim

# Включаем репозитории contrib и non-free
RUN echo "deb http://deb.debian.org/debian bullseye main contrib non-free" > /etc/apt/sources.list

# Обновляем список пакетов и устанавливаем необходимые зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    unrar \
    && rm -rf /var/lib/apt/lists/*

# Создаём пользователя для повышения безопасности
RUN useradd -ms /bin/bash celeryuser

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код бота
COPY . .

# Устанавливаем переменные окружения по умолчанию
ENV FINAL_WIDTH=900
ENV FINAL_HEIGHT=1200
ENV ASPECT_RATIO_TOLERANCE=0.05

# Переключаемся на созданного пользователя
USER celeryuser

# Команда для запуска бота
CMD ["python", "bot.py"]
