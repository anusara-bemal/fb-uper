# Dailymotion Video Downloader Telegram Bot

This is a Telegram bot that can download videos from Dailymotion links.

## Setup Instructions

1. Install Python 3.7 or higher
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a new bot on Telegram:
   - Open Telegram and search for "@BotFather"
   - Send `/newbot` command
   - Follow the instructions to create your bot
   - Copy the bot token provided by BotFather

4. Create a `.env` file in the project root and add your bot token:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

5. Run the bot:
   ```
   python bot.py
   ```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to get a welcome message
3. Send `/help` to see usage instructions
4. Send any Dailymotion video link to download the video

## Features

- Downloads videos from Dailymotion links
- Sends the video directly in Telegram
- Shows video title and duration
- Supports best quality video download
- Error handling for invalid links

## Note

Make sure you have enough disk space for temporary video storage while downloading. 