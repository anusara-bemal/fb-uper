# Dailymotion Video Downloader Bot

A Telegram userbot that downloads videos from Dailymotion and sends them with a watermark.

## Features
- Downloads Dailymotion videos
- Adds a watermark to videos
- Supports video quality up to 720p
- Shows download and upload progress
- Optional logging to a channel

## Setup Instructions

### 1. Get Telegram API Credentials
1. Go to https://my.telegram.org/
2. Log in with your phone number
3. Click on 'API Development Tools'
4. Create a new application
5. Copy the `api_id` and `api_hash`

### 2. Generate Session String
1. Clone this repository
2. Copy `.env.example` to `.env`
3. Add your `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE` to `.env`
4. Set `GENERATE_SESSION=yes` in `.env`
5. Run `python userbot.py`
6. Enter the code sent to your Telegram
7. Copy the session string that is generated

### 3. Deploy to Coolify
1. Create a new service in Coolify
2. Select 'Docker' as deployment type
3. Add your repository
4. Add the following environment variables:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `TELEGRAM_SESSION_STRING` (from step 2)
   - `LOG_CHANNEL_ID` (optional)
5. Deploy the service

## Usage
1. Start a chat with your account
2. Send a Dailymotion video link
3. Wait for the bot to process and send the video
4. The video will be sent with a watermark

## Commands
- `/start` - Shows welcome message
- `/help` - Shows help information

## Notes
- Videos are limited to 2GB (Telegram's limit)
- The bot adds a "zoco_lk" watermark to all videos
- FFmpeg is required for watermark functionality

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