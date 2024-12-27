
# Image Resizer Bot

A Telegram bot for processing square-like images in archives. It resizes them to a 3:4 aspect ratio with a white background.

## Features
- Adjusts square-like images to 3:4 format (default 900x1200).
- Adds a white background if necessary.
- Accepts ZIP and RAR archives.
- Returns processed images in a ZIP archive.

## Requirements
- Python 3.9+
- Telegram bot token (set in `.env` file or as an environment variable).

## Installation

### Locally
1. Clone the repository:
   ```bash
   git clone https://github.com/akadorkin/image-resizer-bot.git
   cd image-resizer-bot
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file:
   ```plaintext
   BOT_TOKEN=your_telegram_bot_token
   FINAL_WIDTH=900
   FINAL_HEIGHT=1200
   ASPECT_RATIO_TOLERANCE=0.05
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

### Using Docker
1. Build the Docker image:
   ```bash
   docker build -t image-resizer-bot .
   ```
2. Run the container, for example, if you need to limit memory to 512 megabytes:
   ```bash
   docker run -d --env-file .env --memory=512m image-resizer-bot 
   ```

## Notes
- `.env` file must not be committed to the repository.
- Use `.env.example` as a template for your configuration.

## License
MIT
