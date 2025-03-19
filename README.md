# Dailymotion Video Downloader UserBot

A Telegram UserBot that automatically downloads Dailymotion videos, adds a watermark, and sends them back to the user. It can handle videos up to 2GB, making it superior to regular bots that have a 50MB limit.

## Deployable to Coolify

This application is configured to be easily deployed on Coolify, a self-hosted PaaS platform.

## Setup Instructions

### 1. Local Setup for Session String Generation

Before deploying to Coolify, you need to generate a session string locally:

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file using `.env.example` as a template
4. Fill in your Telegram API credentials and phone number
5. Set `GENERATE_SESSION=yes` in your `.env` file
6. Run `python userbot.py`
7. Enter the verification code sent to your Telegram
8. Copy the session string that is displayed

### 2. Coolify Deployment

1. Create a new application in Coolify
2. Select "Deploy from Git repository" and provide your repo URL
3. Set the following environment variables:

```
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_STRING=your_session_string_from_step_1
LOG_CHANNEL_ID=your_log_channel_id (optional)
```

4. Deploy the application

## Features

- Downloads and processes Dailymotion videos
- Adds a watermark with your brand/username
- Supports videos up to 2GB in size
- Can forward video copies to a log channel
- Works with links from dailymotion.com and dai.ly

## Usage

Once deployed, you can:

1. Send a Dailymotion video link to your UserBot
2. The bot will download the video, add a watermark, and send it back
3. All temporary files are automatically cleaned up

## Environment Variables

| Variable | Description |
|----------|-------------|
| TELEGRAM_API_ID | Your Telegram API ID from my.telegram.org |
| TELEGRAM_API_HASH | Your Telegram API Hash from my.telegram.org |
| TELEGRAM_SESSION_STRING | Auth session string (generated in Step 1) |
| LOG_CHANNEL_ID | Optional channel ID for logging downloads |

## Troubleshooting

- If the bot doesn't start, check that your session string is valid
- For log channel functionality, ensure the bot is an admin in the channel
- If videos fail to download, ensure ffmpeg is installed correctly

## License

This project is licensed under the MIT License - see the LICENSE file for details. 