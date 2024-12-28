# 📸 Telegram Image Resizer Bot

**Telegram Image Resizer Bot** is a powerful and user-friendly bot that allows you to effortlessly resize your images and archives directly within Telegram. Whether you need to adjust individual photos or batch process multiple images within ZIP or RAR archives, this bot has got you covered!

---

## 🚀 Features

- **Archive Processing:** Upload ZIP or RAR archives containing multiple images and receive a resized version.
- **Individual Image Resizing:** Send images as documents (JPG, PNG, WEBP) and get them resized instantly.
- **Aspect Ratio Preservation:** Resizes images from **1×1** to **3×4 (900×1200)** while maintaining the original aspect ratio with a white background.
- **Supported Formats:** JPG, PNG, WEBP.
- **User-Friendly Commands:** Simple `/start` command to get started and `/stats` command to view statistics.
- **Dockerized Deployment:** Easily deploy and manage the bot using Docker and Docker Compose.
- **Robust Error Handling:** Informative messages guide you through any issues during processing.

---

## 🛠️ Technologies Used

- **Python 3.9**
- **[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)**
- **[Celery](https://docs.celeryproject.org/)**
- **[Redis](https://redis.io/)**
- **[Pillow](https://python-pillow.org/)**
- **Docker & Docker Compose**

---

## 📥 Installation & Setup

### 📋 Prerequisites

- **Docker:** Ensure you have Docker installed. [Download Docker](https://www.docker.com/get-started)
- **Docker Compose:** Typically comes bundled with Docker Desktop. [Install Docker Compose](https://docs.docker.com/compose/install/)
- **Telegram Bot Token:** Create a new bot using [BotFather](https://t.me/BotFather) on Telegram and obtain your bot token.

### 🔧 Configuration

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/image-resizer-bot.git
   cd image-resizer-bot
   ```

2. **Create a `.env` File:**

   Create a `.env` file in the root directory of the project and add the following environment variables:

   ```env
   BOT_TOKEN=your_telegram_bot_token_here
   CELERY_BROKER_URL=redis://redis:6379/0
   CELERY_BACKEND_URL=redis://redis:6379/0
   FINAL_WIDTH=900
   FINAL_HEIGHT=1200
   ASPECT_RATIO_TOLERANCE=0.15
   ```

   Replace `your_telegram_bot_token_here` with the token you received from BotFather.

3. **Initialize `stats.json`:**

   Initialize the statistics file by creating a `stats` directory and adding a `stats.json` file:

   ```bash
   mkdir stats
   echo '{
       "users": [],
       "archives": 0,
       "images": 0,
       "resizes": 0,
       "top_archives": []
   }' > stats/stats.json
   ```

---

### 🐳 Running with Docker Compose

1. **Build and Start the Containers:**

   ```bash
   docker-compose up -d --build
   ```

2. **Verify Containers are Running:**

   ```bash
   docker-compose ps
   ```

   You should see the following containers running:

   - `image-resizer-bot`
   - `celery-worker`
   - `redis`

3. **Check Logs for Any Issues:**

   ```bash
   # View bot logs
   docker logs -f image-resizer-bot

   # View Celery worker logs
   docker logs -f celery-worker
   ```

---

## 🎮 Usage

### 🔰 Start the Bot

Send the `/start` command to your bot in Telegram to receive instructions.

### 📁 Processing Archives

- **Send a ZIP or RAR Archive:**  
  Upload a ZIP or RAR archive containing your images as a document or images.

- **Receive Resized Archive:**  
  The bot will process the archive and return a new archive with resized images or files with images.

### 🖼️ Processing Individual Images

- **Send Images as Documents:**  
  Upload images (JPG, PNG, WEBP) as documents to retain original filenames.

- **Receive Resized Images:**  
  The bot will resize the images and send them back with a `resized_{timestamp}_` prefix.

### 📊 View Statistics

Send the `/stats` command to view the bot's statistics:

```plaintext
/stats
```

Displays information such as:

- Unique Users
- Archives Processed
- Images Processed
- Images Resized
- Top 3 Largest Archives

---

## 🗂️ Project Structure

```plaintext
/app
├── bot.py               # Telegram bot logic
├── tasks.py             # Celery tasks for processing
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose configuration
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables
└── stats
    └── stats.json       # Statistics data
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork the Repository**
2. **Create a Feature Branch:**

   ```bash
   git checkout -b feature/YourFeature
   ```

3. **Commit Your Changes:**

   ```bash
   git commit -m "Add some feature"
   ```

4. **Push to the Branch:**

   ```bash
   git push origin feature/YourFeature
   ```

5. **Open a Pull Request**

Ensure your code follows the project's coding standards and includes appropriate tests.

---

## 📜 License

This project is licensed under the MIT License.

---

## 🔗 Useful Links

- [GitHub Repository](https://github.com/yourusername/image-resizer-bot)
- [Docker Documentation](https://docs.docker.com/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [python-telegram-bot Documentation](https://python-telegram-bot.readthedocs.io/)
