import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
from dotenv import load_dotenv
import re
import subprocess
import shutil
from PIL import Image, ImageDraw, ImageFont
import time

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Get your bot token from environment variable
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
LOG_CHANNEL = os.getenv('LOG_CHANNEL_ID') # Get log channel ID from env variable

# Create directories if they don't exist
DOWNLOAD_DIR = 'downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Print debug info at startup
print(f"Bot token available: {bool(TOKEN)}")
print(f"Log channel configured: {bool(LOG_CHANNEL)} - Value: {LOG_CHANNEL}")

def is_dailymotion_url(url):
    """Check if the URL is a valid Dailymotion URL."""
    patterns = [
        r'https?://(?:www\.)?dailymotion\.com/(?:video|embed/video)/[a-zA-Z0-9]+',
        r'https?://(?:www\.)?dai\.ly/[a-zA-Z0-9]+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def check_ffmpeg():
    """Check if FFmpeg is available"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def create_watermark_image(output_path, text="zoco_lk"):
    """Create a simple transparent image with text."""
    try:
        # Create an even smaller transparent image (further reduced size)
        img = Image.new('RGBA', (80, 25), color=(255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        
        # Try to create a font with smaller size
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except:
            font = None  # Will use default font if Arial not available
        
        # Add text with better visibility and center it properly
        # White text with semi-transparency
        d.text((8, 5), text, font=font, fill=(255, 255, 255, 200))
        
        # Save the image
        img.save(output_path, 'PNG')
        return True
    except Exception as e:
        logging.error(f"Error creating watermark image: {str(e)}")
        return False

def add_watermark_to_video(input_video, output_video, watermark_image):
    """Add watermark image to video that scrolls upward."""
    try:
        # Overlay with animated position making the watermark scroll up
        # Position back to the right side (main_w-overlay_w-20)
        cmd = f'ffmpeg -y -i "{input_video}" -i "{watermark_image}" -filter_complex "[0:v][1:v] overlay=main_w-overlay_w-20:main_h-overlay_h-10-mod(t*30\,main_h+overlay_h+50):enable=\'between(t,0,999999)\'" -c:v libx264 -preset ultrafast -c:a copy "{output_video}"'
        
        print("Running FFmpeg command:", cmd)
        
        # Run the command
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()
        
        # Check if output file was created
        if os.path.exists(output_video) and os.path.getsize(output_video) > 0:
            print("Watermark added successfully!")
            return True
        else:
            print("FFmpeg failed to create output file")
            print("STDERR:", stderr.decode() if stderr else "")
            return False
            
    except Exception as e:
        logging.error(f"Error adding watermark: {str(e)}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        'Hi! I am a Dailymotion video downloader bot. '
        'Just send me a Dailymotion video link and I will download it for you!'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        'To download a Dailymotion video:\n'
        '1. Copy the Dailymotion video link (dai.ly or dailymotion.com)\n'
        '2. Send it to me\n'
        '3. Wait for the video to be downloaded and sent back to you'
    )

async def send_to_log_channel(context, video_path, caption):
    """Helper function to send video to log channel"""
    if not LOG_CHANNEL:
        print("No log channel configured")
        return False
        
    try:
        print(f"Attempting to send video to log channel: {LOG_CHANNEL}")
        # Reopen the file for sending
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=LOG_CHANNEL,
                video=video_file,
                caption=caption,
                supports_streaming=True,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=60,
                pool_timeout=60
            )
        print(f"Successfully sent video to log channel {LOG_CHANNEL}")
        return True
    except Exception as e:
        print(f"Error sending to log channel: {str(e)}")
        return False

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download video from Dailymotion link."""
    message = update.message
    url = message.text.strip()
    
    # Debugging log channel
    print(f"Current LOG_CHANNEL value: {LOG_CHANNEL}")

    if not is_dailymotion_url(url):
        await message.reply_text('Please send a valid Dailymotion video link.\nExample formats:\n- https://dai.ly/xxxxx\n- https://www.dailymotion.com/video/xxxxx')
        return

    status_message = await message.reply_text('Starting download... Please wait.')
    
    # Check if FFmpeg is available
    has_ffmpeg = check_ffmpeg()
    if not has_ffmpeg:
        await status_message.edit_text('FFmpeg not found. Videos will be sent without watermark.')
        print("FFmpeg not found!")
    else:
        print("FFmpeg found and available")

    try:
        # Generate unique filenames
        temp_video_path = os.path.join(DOWNLOAD_DIR, f'temp_video_{message.message_id}.mp4')
        watermarked_video_path = os.path.join(DOWNLOAD_DIR, f'watermarked_video_{message.message_id}.mp4')
        watermark_image_path = os.path.join(DOWNLOAD_DIR, f'watermark_{message.message_id}.png')

        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': temp_video_path,
            'socket_timeout': 30,  # Increase socket timeout
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                print("Attempting to download video...")
                info = ydl.extract_info(url, download=True)
                print("Video info extracted successfully")
            except Exception as download_err:
                print(f"Error during download: {str(download_err)}")
                raise  # Re-raise the exception to be caught by the outer try-except
            
            if has_ffmpeg:
                await status_message.edit_text('Download complete. Adding watermark...')
                print(f"Video downloaded to: {temp_video_path}")
                
                # Create watermark image
                if create_watermark_image(watermark_image_path, "zoco_lk"):
                    print(f"Watermark image created at: {watermark_image_path}")
                    print(f"Attempting to add watermark to: {watermarked_video_path}")
                    
                    # Add watermark to video
                    if add_watermark_to_video(temp_video_path, watermarked_video_path, watermark_image_path):
                        print("Watermark added successfully")
                        # Send the watermarked video file
                        video_message = await message.reply_video(
                            video=open(watermarked_video_path, 'rb'),
                            caption=f"Title: {info.get('title', 'Unknown')}\nDuration: {info.get('duration', 0)} seconds"
                        )
                        await status_message.edit_text('Video sent successfully!')
                        
                        # Send to log channel
                        user_info = f"User: @{message.from_user.username or 'No Username'} ({message.from_user.id})"
                        log_caption = f"Title: {info.get('title', 'Unknown')}\nRequested by: {user_info}\nURL: {url}"
                        await send_to_log_channel(context, watermarked_video_path, log_caption)
                            
                        # Clean up
                        for file_path in [temp_video_path, watermark_image_path]:
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                    print(f"Deleted file: {file_path}")
                                except Exception as del_err:
                                    print(f"Error deleting file {file_path}: {del_err}")
                                    # Try again after a short delay
                                    time.sleep(1)
                                    try:
                                        os.remove(file_path)
                                        print(f"Successfully deleted file on retry: {file_path}")
                                    except Exception as retry_err:
                                        print(f"Failed to delete file after retry: {file_path}")
                    else:
                        print("Failed to add watermark")
                        # If watermarking fails, send the original video
                        await status_message.edit_text('Could not add watermark. Sending original video...')
                        video_message = await message.reply_video(
                            video=open(temp_video_path, 'rb'),
                            caption=f"Title: {info.get('title', 'Unknown')}\nDuration: {info.get('duration', 0)} seconds"
                        )
                        
                        # Send to log channel
                        user_info = f"User: @{message.from_user.username or 'No Username'} ({message.from_user.id})"
                        log_caption = f"Title: {info.get('title', 'Unknown')}\nRequested by: {user_info}\nURL: {url}\nNote: Original video (watermark failed)"
                        await send_to_log_channel(context, temp_video_path, log_caption)
                        
                        # Clean up
                        for file_path in [temp_video_path, watermark_image_path]:
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                    print(f"Deleted file: {file_path}")
                                except Exception as del_err:
                                    print(f"Error deleting file {file_path}: {del_err}")
                                    # Try again after a short delay
                                    time.sleep(1)
                                    try:
                                        os.remove(file_path)
                                        print(f"Successfully deleted file on retry: {file_path}")
                                    except Exception as retry_err:
                                        print(f"Failed to delete file after retry: {file_path}")
                else:
                    print("Failed to create watermark image")
                    await status_message.edit_text('Could not create watermark. Sending original video...')
                    video_message = await message.reply_video(
                        video=open(temp_video_path, 'rb'),
                        caption=f"Title: {info.get('title', 'Unknown')}\nDuration: {info.get('duration', 0)} seconds"
                    )
                    
                    # Send to log channel
                    user_info = f"User: @{message.from_user.username or 'No Username'} ({message.from_user.id})"
                    log_caption = f"Title: {info.get('title', 'Unknown')}\nRequested by: {user_info}\nURL: {url}\nNote: Original video (watermark creation failed)"
                    await send_to_log_channel(context, temp_video_path, log_caption)
                    
                    # Clean up
                    for file_path in [temp_video_path, watermark_image_path]:
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                print(f"Deleted file: {file_path}")
                            except Exception as del_err:
                                print(f"Error deleting file {file_path}: {del_err}")
                                # Try again after a short delay
                                time.sleep(1)
                                try:
                                    os.remove(file_path)
                                    print(f"Successfully deleted file on retry: {file_path}")
                                except Exception as retry_err:
                                    print(f"Failed to delete file after retry: {file_path}")
            else:
                # Send without watermark
                await status_message.edit_text('Download complete! Sending video...')
                video_message = await message.reply_video(
                    video=open(temp_video_path, 'rb'),
                    caption=f"Title: {info.get('title', 'Unknown')}\nDuration: {info.get('duration', 0)} seconds"
                )
                
                # Send to log channel
                user_info = f"User: @{message.from_user.username or 'No Username'} ({message.from_user.id})"
                log_caption = f"Title: {info.get('title', 'Unknown')}\nRequested by: {user_info}\nURL: {url}\nNote: No watermark (FFmpeg not available)"
                await send_to_log_channel(context, temp_video_path, log_caption)
                
                # Clean up the temporary file
                for file_path in [temp_video_path]:
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"Deleted file: {file_path}")
                        except Exception as del_err:
                            print(f"Error deleting file {file_path}: {del_err}")
                            # Try again after a short delay
                            time.sleep(1)
                            try:
                                os.remove(file_path)
                                print(f"Successfully deleted file on retry: {file_path}")
                            except Exception as retry_err:
                                print(f"Failed to delete file after retry: {file_path}")

    except Exception as e:
        error_message = str(e)
        logging.error(f"Error downloading video: {error_message}")
        await status_message.edit_text(f'Error downloading video: {error_message}')
        # Clean up any remaining files
        for file_path in [temp_video_path, watermarked_video_path, watermark_image_path]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted file during error cleanup: {file_path}")
                except Exception as del_err:
                    print(f"Error deleting file {file_path}: {del_err}")
                    # Try again after a short delay
                    time.sleep(1)
                    try:
                        os.remove(file_path)
                        print(f"Successfully deleted file on retry: {file_path}")
                    except Exception as retry_err:
                        print(f"Failed to delete file after retry: {file_path}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logging.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("Sorry, something went wrong. Please try again later.")

def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token with increased timeout
    application = Application.builder().token(TOKEN).connect_timeout(30.0).read_timeout(30.0).write_timeout(30.0).pool_timeout(30.0).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    print("Bot started! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()