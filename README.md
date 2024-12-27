# Image Resizer Bot

A Telegram bot for processing square-like images in archives. It resizes them to a 3:4 aspect ratio with a white background.

## Features
- Adjusts square-like images to a 3:4 format (default: 900x1200).
- Adds a white background if necessary.
- Accepts ZIP and RAR archives.
- Returns processed images in a ZIP archive.

## Requirements
- Python 3.х.
- Telegram bot token (set via `.env` file or environment variables).

## Installation

### Locally
1. Clone the repository:
   ```bash
   git clone https://github.com/akadorkin/image-resizer-bot.git
   cd image-resizer-bot
   ```
2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
4. Create a `.env` file with the following content:
   ```plaintext
   BOT_TOKEN=your_telegram_bot_token
   FINAL_WIDTH=900
   FINAL_HEIGHT=1200
   ASPECT_RATIO_TOLERANCE=0.05
   ```
5. Run the bot:
   ```bash
   python3 bot.py
   ```

6. **Optional: Running in the background**
   To run the bot in the background, use `nohup`:
   ```bash
   nohup python3 bot.py > bot.log 2>&1 &
   ```

### Using Docker
1. Build the Docker image:
   ```bash
   docker build -t image-resizer-bot .
   ```
2. Run the container (for example, with a memory limit of 512MB):
   ```bash
   docker run -d --env-file .env --memory=512m image-resizer-bot
   ```

   If you don't want to use a `.env` file, you can specify variables directly:
   ```bash
   docker run -d -e BOT_TOKEN=your_telegram_bot_token -e FINAL_WIDTH=900 -e FINAL_HEIGHT=1200 -e ASPECT_RATIO_TOLERANCE=0.05 image-resizer-bot
   ```

## Notes
- Use `.env.example` as a template for your configuration.
- Ensure that your system has Python 3.х.

## License
MIT
