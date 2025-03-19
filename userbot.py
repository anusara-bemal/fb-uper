import os
import logging
import asyncio
from telethon import TelegramClient, events, utils
from telethon.tl.types import DocumentAttributeVideo
from telethon.sessions import StringSession
import yt_dlp
from dotenv import load_dotenv
import re
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Get Telegram API credentials
API_ID = os.getenv('TELEGRAM_API_ID')  # Get this from https://my.telegram.org/
API_HASH = os.getenv('TELEGRAM_API_HASH')  # Get this from https://my.telegram.org/
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE')  # Your phone number including country code
SESSION_STRING = os.getenv('TELEGRAM_SESSION_STRING')  # Session string for headless auth
LOG_CHANNEL = os.getenv('LOG_CHANNEL_ID')  # Log channel username or ID

# Create directories if they don't exist
DOWNLOAD_DIR = 'downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Print debug info at startup
print(f"API credentials available: {bool(API_ID) and bool(API_HASH)}")
print(f"Session string available: {bool(SESSION_STRING)}")
print(f"Phone number configured: {bool(PHONE_NUMBER)}")
print(f"Log channel configured: {bool(LOG_CHANNEL)} - Value: {LOG_CHANNEL}")

def is_dailymotion_url(url):
    """Check if the URL is a valid Dailymotion URL."""
    patterns = [
        r'https?://(?:www\.)?dailymotion\.com/(?:video|embed/video)/[a-zA-Z0-9]+',
        r'https?://(?:www\.)?dai\.ly/[a-zA-Z0-9]+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def check_ffmpeg():
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def create_watermark_image(output_path, text="zoco_lk"):
    """Create a simple transparent image with text."""
    try:
        # Create a transparent image
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
    """Add watermark image to video that scrolls upward using FFmpeg."""
    try:
        # Restore scrolling watermark but keep optimized encoding settings
        cmd = f'ffmpeg -y -i "{input_video}" -i "{watermark_image}" -filter_complex "[0:v][1:v] overlay=main_w-overlay_w-10:main_h-overlay_h-10-mod(t*8\,main_h+overlay_h):enable=\'between(t,0,999999)\'" -c:v libx264 -preset veryfast -crf 30 -c:a aac -b:a 128k "{output_video}"'
        
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

# Progress callback for upload
async def callback(current, total, status_message, action="Uploading"):
    """Update status message with progress percentage for uploads"""
    percent = int(current * 100 / total)
    # Update every 5% to avoid flooding
    if percent % 5 == 0:
        await status_message.edit(f'{action} progress: {percent}%')

# Progress hook for yt-dlp download
def download_progress_hook(d, status_message):
    """Progress hook for yt-dlp to update download status"""
    if d['status'] == 'downloading':
        try:
            percent = d.get('_percent_str', '0%').strip()
            # Convert "100.0%" to just "100%"
            percent = percent.replace('.0', '')
            elapsed = d.get('_elapsed_str', '00:00')
            speed = d.get('_speed_str', '0 KiB/s')
            eta = d.get('_eta_str', '00:00')
            
            if '_percent_str' in d and not percent.startswith('100'):
                # Use asyncio.create_task to avoid blocking
                asyncio.create_task(
                    status_message.edit(
                        f'⬇️ Downloading: {percent}\n'
                        f'⏱️ Elapsed: {elapsed}\n'
                        f'🚀 Speed: {speed}\n'
                        f'⏳ ETA: {eta}'
                    )
                )
        except Exception as e:
            print(f"Error updating download progress: {e}")

async def download_and_process_video(client, event, url):
    """Download and process a Dailymotion video."""
    # Send initial status
    status_message = await event.reply('🔍 Analyzing video link...')
    
    # Check if FFmpeg is available
    has_ffmpeg = check_ffmpeg()
    if not has_ffmpeg:
        await status_message.edit('⚠️ FFmpeg not found. Videos will be sent without watermark.')
        print("FFmpeg not found!")
    else:
        print("FFmpeg found and available")

    # Initialize file paths to None
    temp_video_path = None
    watermarked_video_path = None
    watermark_image_path = None
    sender = await event.get_sender()
    sender_id = str(sender.id)
    
    try:
        # Generate unique filenames
        message_id = event.id
        temp_video_path = os.path.join(DOWNLOAD_DIR, f'temp_video_{sender_id}_{message_id}.mp4')
        watermarked_video_path = os.path.join(DOWNLOAD_DIR, f'watermarked_video_{sender_id}_{message_id}.mp4')
        watermark_image_path = os.path.join(DOWNLOAD_DIR, f'watermark_{sender_id}_{message_id}.png')

        # Set download options with optimized settings
        ydl_opts = {
            'format': 'best[height<=480]/bestvideo[height<=480]+bestaudio/best',  # Limit to 480p for much faster upload
            'outtmpl': temp_video_path,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'progress_hooks': [lambda d: download_progress_hook(d, status_message)]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await status_message.edit('🔄 Fetching video information...')
            print("Attempting to download video...")
            info = ydl.extract_info(url, download=True)
            print("Video info extracted successfully")
            
            # Check file size
            if os.path.exists(temp_video_path):
                file_size_mb = os.path.getsize(temp_video_path) / (1024 * 1024)
                print(f"Downloaded file size: {file_size_mb:.2f} MB")
                
                if file_size_mb > 1900:  # Close to Telegram's 2GB limit
                    await status_message.edit(f'⚠️ Warning: Video is very large ({file_size_mb:.2f} MB), close to Telegram\'s 2GB limit.')
            
            if has_ffmpeg:
                await status_message.edit('✅ Download complete! 🎬 Adding watermark...')
                print(f"Video downloaded to: {temp_video_path}")
                
                # Create watermark image
                if create_watermark_image(watermark_image_path, "zoco_lk"):
                    print(f"Watermark image created at: {watermark_image_path}")
                    print(f"Attempting to add watermark to: {watermarked_video_path}")
                    
                    # Add watermark to video
                    if add_watermark_to_video(temp_video_path, watermarked_video_path, watermark_image_path):
                        print("Watermark added successfully")
                        
                        # Upload the watermarked video
                        video_title = info.get('title', 'Unknown')
                        await status_message.edit(f'📤 Starting upload: "{video_title}" ({file_size_mb:.2f} MB)')
                        
                        # Get video metadata
                        video_duration = info.get('duration', 0)
                        video_width = info.get('width', 0)
                        video_height = info.get('height', 0)
                        
                        attributes = [
                            DocumentAttributeVideo(
                                duration=video_duration,
                                w=video_width,
                                h=video_height,
                                supports_streaming=True
                            )
                        ]
                        
                        # Upload the video with progress callback
                        await client.send_file(
                            event.chat_id,
                            watermarked_video_path,
                            caption=f"📹 Title: {video_title}\n⏱️ Duration: {video_duration} seconds",
                            attributes=attributes,
                            progress_callback=lambda current, total: asyncio.create_task(
                                callback(current, total, status_message)
                            )
                        )
                        
                        await status_message.edit('✅ Video sent successfully!')
                        
                        # Send to log channel if configured - using forward instead of re-upload
                        if LOG_CHANNEL:
                            try:
                                # Forward the message to log channel instead of re-uploading
                                forwarded_msg = await client.forward_messages(
                                    LOG_CHANNEL,
                                    messages=event.message,
                                    from_peer=event.chat_id
                                )
                                # Edit the forwarded message with additional info
                                user_info = f"User: @{sender.username or 'No Username'} ({sender.id})"
                                await forwarded_msg.edit(
                                    f"Title: {video_title}\nRequested by: {user_info}\nURL: {url}"
                                )
                                print(f"Successfully forwarded to log channel {LOG_CHANNEL}")
                            except Exception as log_err:
                                print(f"Error forwarding to log channel: {str(log_err)}")
                    else:
                        print("Failed to add watermark")
                        # If watermarking fails, send the original video
                        await status_message.edit('⚠️ Could not add watermark. Sending original video...')
                        
                        # Get video metadata
                        video_duration = info.get('duration', 0)
                        video_width = info.get('width', 0)
                        video_height = info.get('height', 0)
                        video_title = info.get('title', 'Unknown')
                        
                        attributes = [
                            DocumentAttributeVideo(
                                duration=video_duration,
                                w=video_width,
                                h=video_height,
                                supports_streaming=True
                            )
                        ]
                        
                        # Upload the original video with progress callback
                        await client.send_file(
                            event.chat_id,
                            temp_video_path,
                            caption=f"📹 Title: {video_title}\n⏱️ Duration: {video_duration} seconds",
                            attributes=attributes,
                            progress_callback=lambda current, total: asyncio.create_task(
                                callback(current, total, status_message)
                            )
                        )
                        
                        await status_message.edit('✅ Video sent successfully!')
                        
                        # Forward to log channel if configured
                        if LOG_CHANNEL:
                            try:
                                forwarded_msg = await client.forward_messages(
                                    LOG_CHANNEL,
                                    messages=event.message,
                                    from_peer=event.chat_id
                                )
                                user_info = f"User: @{sender.username or 'No Username'} ({sender.id})"
                                await forwarded_msg.edit(
                                    f"Title: {video_title}\nRequested by: {user_info}\nURL: {url}\nNote: Original video (watermark failed)"
                                )
                            except Exception as log_err:
                                print(f"Error forwarding to log channel: {str(log_err)}")
                else:
                    print("Failed to create watermark image")
                    await status_message.edit('⚠️ Could not create watermark. Sending original video...')
                    
                    # Get video metadata
                    video_duration = info.get('duration', 0)
                    video_width = info.get('width', 0)
                    video_height = info.get('height', 0)
                    video_title = info.get('title', 'Unknown')
                    
                    attributes = [
                        DocumentAttributeVideo(
                            duration=video_duration,
                            w=video_width,
                            h=video_height,
                            supports_streaming=True
                        )
                    ]
                    
                    # Upload the original video with progress callback
                    await client.send_file(
                        event.chat_id,
                        temp_video_path,
                        caption=f"📹 Title: {video_title}\n⏱️ Duration: {video_duration} seconds",
                        attributes=attributes,
                        progress_callback=lambda current, total: asyncio.create_task(
                            callback(current, total, status_message)
                        )
                    )
                    
                    await status_message.edit('✅ Video sent successfully!')
                    
                    # Forward to log channel if configured
                    if LOG_CHANNEL:
                        try:
                            forwarded_msg = await client.forward_messages(
                                LOG_CHANNEL,
                                messages=event.message,
                                from_peer=event.chat_id
                            )
                            user_info = f"User: @{sender.username or 'No Username'} ({sender.id})"
                            await forwarded_msg.edit(
                                f"Title: {video_title}\nRequested by: {user_info}\nURL: {url}\nNote: Original video (watermark creation failed)"
                            )
                        except Exception as log_err:
                            print(f"Error forwarding to log channel: {str(log_err)}")
            else:
                # Send without watermark
                await status_message.edit('✅ Download complete! Sending video...')
                
                # Get video metadata
                video_duration = info.get('duration', 0)
                video_width = info.get('width', 0)
                video_height = info.get('height', 0)
                video_title = info.get('title', 'Unknown')
                
                attributes = [
                    DocumentAttributeVideo(
                        duration=video_duration,
                        w=video_width,
                        h=video_height,
                        supports_streaming=True
                    )
                ]
                
                # Upload the original video with progress callback
                await client.send_file(
                    event.chat_id,
                    temp_video_path,
                    caption=f"📹 Title: {video_title}\n⏱️ Duration: {video_duration} seconds",
                    attributes=attributes,
                    progress_callback=lambda current, total: asyncio.create_task(
                        callback(current, total, status_message)
                    )
                )
                
                await status_message.edit('✅ Video sent successfully!')
                
                # Forward to log channel if configured
                if LOG_CHANNEL:
                    try:
                        forwarded_msg = await client.forward_messages(
                            LOG_CHANNEL,
                            messages=event.message,
                            from_peer=event.chat_id
                        )
                        user_info = f"User: @{sender.username or 'No Username'} ({sender.id})"
                        await forwarded_msg.edit(
                            f"Title: {video_title}\nRequested by: {user_info}\nURL: {url}\nNote: No watermark (FFmpeg not available)"
                        )
                    except Exception as log_err:
                        print(f"Error forwarding to log channel: {str(log_err)}")

    except Exception as e:
        error_message = str(e)
        logging.error(f"Error downloading video: {error_message}")
        await status_message.edit(f'❌ Error downloading video: {error_message}')
    
    finally:
        # Clean up any remaining files
        for file_path in [temp_video_path, watermarked_video_path, watermark_image_path]:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted file during cleanup: {file_path}")
                except Exception as del_err:
                    print(f"Error deleting file {file_path}: {del_err}")
                    # Try again after a short delay
                    time.sleep(1)
                    try:
                        os.remove(file_path)
                        print(f"Successfully deleted file on retry: {file_path}")
                    except Exception as retry_err:
                        print(f"Failed to delete file after retry: {file_path}")

# Function to generate a session string (run this locally once, then use in Coolify)
async def generate_session_string():
    """Generate a session string for headless authentication."""
    if not API_ID or not API_HASH or not PHONE_NUMBER:
        print("Error: API_ID, API_HASH, and PHONE_NUMBER must be set to generate a session string.")
        return
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(phone=PHONE_NUMBER)
    
    session_str = client.session.save()
    print(f"\nYour session string is:\n{session_str}\n")
    print("Add this to your Coolify environment variables as TELEGRAM_SESSION_STRING")
    
    await client.disconnect()

async def main():
    """Main function to run the user bot."""
    # Check if we need to generate a session string
    if os.getenv('GENERATE_SESSION') == 'yes':
        await generate_session_string()
        return
    
    # Use session string if available, otherwise use regular authentication
    if SESSION_STRING:
        # Create the client with session string (for headless environments like Coolify)
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        print("Using session string for authentication (headless mode)")
    else:
        # Create the client with file session (for local development)
        client = TelegramClient('dailymotion_user_session', API_ID, API_HASH)
        print("Using file-based session for authentication")
    
    # Start the client
    await client.start()
    
    # Check if the client is connected and handle authentication
    if not await client.is_user_authorized():
        if SESSION_STRING:
            print("Error: Session string is invalid or expired.")
            return
        
        # If not authorized and in interactive mode, try logging in
        if not PHONE_NUMBER:
            print("Error: PHONE_NUMBER is required for interactive login.")
            return
            
        await client.send_code_request(PHONE_NUMBER)
        print(f"Please enter the code sent to {PHONE_NUMBER}")
        code = input("Enter the code: ")
        await client.sign_in(PHONE_NUMBER, code)
    
    me = await client.get_me()
    print(f"Logged in as {me.first_name} ({me.username or 'no username'})")
    
    # Register the message handler for Dailymotion links
    @client.on(events.NewMessage(pattern=r'https?://(?:www\.)?(?:dai\.ly|dailymotion\.com/(?:video|embed/video))/[a-zA-Z0-9]+'))
    async def dailymotion_handler(event):
        url = event.text.strip()
        print(f"Received Dailymotion URL: {url}")
        
        # Process only if it's a valid Dailymotion URL
        if is_dailymotion_url(url):
            await download_and_process_video(client, event, url)
    
    # Register handler for /start command
    @client.on(events.NewMessage(pattern=r'/start'))
    async def start_handler(event):
        await event.reply(
            'Hi! I am a Dailymotion video downloader. '
            'Just send me a Dailymotion video link and I will download it for you!'
        )
    
    # Register handler for /help command
    @client.on(events.NewMessage(pattern=r'/help'))
    async def help_handler(event):
        await event.reply(
            'To download a Dailymotion video:\n'
            '1. Copy the Dailymotion video link (dai.ly or dailymotion.com)\n'
            '2. Send it to me\n'
            '3. Wait for the video to be downloaded and sent back to you\n\n'
            'I can download and send videos up to 2GB in size!'
        )
    
    # Run the client until disconnected
    print("UserBot started! Press Ctrl+C to stop.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("UserBot stopped.") 