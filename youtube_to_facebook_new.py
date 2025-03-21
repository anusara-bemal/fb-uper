import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import yt_dlp
import facebook
from dotenv import load_dotenv
import time
import re
import asyncio
import requests
from datetime import datetime, timedelta
import random
import threading
import json
import pickle

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='bot.log'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Emoji sets for variety
SUCCESS_EMOJIS = ["✅", "🎉", "🚀", "🔥", "⭐", "💯"]
WAITING_EMOJIS = ["⏳", "⌛", "🕒", "⏱️", "🔄"]
DOWNLOAD_EMOJIS = ["📥", "💾", "📁", "🔽", "⬇️"]
UPLOAD_EMOJIS = ["📤", "⬆️", "🌐", "📱", "💫"]

# Global variables for upload state
is_paused = False
current_wait_event = None
skip_requested = False

def random_emoji(emoji_set):
    return random.choice(emoji_set)

# Create an event for pause/resume functionality
pause_event = threading.Event()
pause_event.set()  # Initially not paused

class YouTubeToFacebookBot:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.facebook_token = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN')
        self.facebook_page_id = os.getenv('FACEBOOK_PAGE_ID')
        self.download_path = 'downloads'
        self.cookies_file = 'youtube_cookies.txt'
        self.session_file = 'yt_session.pickle'
        
        # Configure wait time (default 1 hour, can be changed with /setwait command)
        self.wait_time = 3600  # 1 hour in seconds
        
        # Initialize Facebook Graph API
        self.fb = facebook.GraphAPI(access_token=self.facebook_token)
        
        # Create downloads directory if it doesn't exist
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

        # Track current status message and wait message
        self.status_message = None
        self.wait_message = None

    def extract_youtube_url(self, line):
        """Extract YouTube URL from a line"""
        # Remove any VM1403:9 prefix and extra spaces
        line = re.sub(r'^VM\d+:\d+\s*', '', line.strip())
        url_match = re.search(r'https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]+', line)
        if url_match:
            return url_match.group(0)
        return None

    def get_video_id(self, url):
        """Extract video ID from YouTube URL"""
        match = re.search(r'v=([A-Za-z0-9_-]+)', url)
        if match:
            return match.group(1)
        return None

    async def download_youtube_video(self, url, update: Update):
        """Download a YouTube video using yt-dlp with cookies support"""
        try:
            # Check if we have saved cookies
            cookies_exists = os.path.isfile(self.cookies_file)
            session_exists = os.path.isfile(self.session_file)
            
            ydl_opts = {
                'format': 'best',
                'outtmpl': os.path.join(self.download_path, '%(title)s.%(ext)s'),
                'quiet': True,
                'writeinfojson': True,
                'writedescription': True,
                'writethumbnail': True,
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                'nocheckcertificate': True,
                'ignoreerrors': True
            }
            
            # Add cookies file if it exists
            if cookies_exists:
                ydl_opts['cookiefile'] = self.cookies_file
            
            # Load session if exists
            session = None
            if session_exists:
                try:
                    with open(self.session_file, 'rb') as f:
                        session = pickle.load(f)
                        logger.info("Loaded existing YouTube session")
                except Exception as e:
                    logger.error(f"Error loading session: {str(e)}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Try to get video info first
                try:
                    info = ydl.extract_info(url, download=False)
                    
                    # If successful, proceed with download
                    video_title = info['title']
                    duration = info.get('duration', 0)
                    channel = info.get('channel', 'Unknown')
                    upload_date = info.get('upload_date', '')
                    view_count = info.get('view_count', 0)
                    like_count = info.get('like_count', 0)
                    description = info.get('description', '')[:100] + '...' if info.get('description') else ''
                    thumbnail = info.get('thumbnail', '')
                    
                    logger.info(f"Downloading: {video_title}")
                    
                    # Download the video
                    ydl.download([url])
                    
                    # Get the downloaded file path
                    video_path = os.path.join(self.download_path, f"{video_title}.{info['ext']}")
                    logger.info(f"Download completed: {video_path}")
                    
                    video_data = {
                        'path': video_path,
                        'title': video_title,
                        'duration': duration,
                        'channel': channel,
                        'upload_date': upload_date,
                        'views': view_count,
                        'likes': like_count,
                        'description': description,
                        'thumbnail': thumbnail
                    }
                    
                    return video_data
                    
                except Exception as e:
                    error_str = str(e)
                    logger.error(f"Error during info extraction: {error_str}")
                    
                    # Check if the error is related to sign-in requirements
                    if "Sign in to confirm you're not a bot" in error_str:
                        await update.message.reply_text(
                            f"⚠️ <b>Authentication Required!</b>\n\n"
                            f"YouTube is asking to verify you're not a bot. "
                            f"Please use /setcookies command to provide your YouTube cookies.",
                            parse_mode='HTML'
                        )
                    
                    raise
        
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            raise

    async def upload_to_facebook(self, video_path, title, update: Update):
        """Upload video to Facebook Page without status messages"""
        try:
            # Prepare the video file for upload
            with open(video_path, 'rb') as video_file:
                # Upload to Facebook
                url = f"https://graph.facebook.com/v18.0/{self.facebook_page_id}/videos"
                
                # Create form data
                files = {
                    'source': (os.path.basename(video_path), video_file, 'video/mp4')
                }
                
                data = {
                    'title': title,
                    'description': title,
                    'access_token': self.facebook_token
                }
                
                # Upload the video without progress updates
                response = requests.post(url, files=files, data=data)
                
                if response.status_code != 200:
                    raise Exception(f"Facebook API error: {response.text}")
                
                # Parse response JSON
                result = response.json()
            
            logger.info(f"Video uploaded to Facebook. Title: {title}, Post ID: {result.get('id')}")
            return result.get('id')
                
        except Exception as e:
            logger.error(f"Error uploading to Facebook: {str(e)}")
            raise

    async def process_video(self, line, update: Update):
        """Process a single video"""
        try:
            # Extract YouTube URL
            youtube_url = self.extract_youtube_url(line)
            if not youtube_url:
                await update.message.reply_text(
                    f"❌ <b>Error:</b> No valid YouTube URL found in this line", 
                    parse_mode='HTML'
                )
                return None

            # Extract title from the line (everything before the URL)
            custom_title = line.split('https://')[0].strip()
            
            # Get video ID for thumbnail
            video_id = self.get_video_id(youtube_url)
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else None
            
            # Check if paused before starting download
            global pause_event
            if not pause_event.is_set():
                await update.message.reply_text(
                    f"⏸️ <b>Upload process is paused.</b> Use /resume to continue.",
                    parse_mode='HTML'
                )
                # Wait until resumed
                pause_event.wait()
            
            # Show download message
            download_emoji = random_emoji(DOWNLOAD_EMOJIS)
            download_message = await update.message.reply_text(
                f"{download_emoji} <b>Downloading video...</b>",
                parse_mode='HTML'
            )
            
            # Download the video and get its data
            video_data = await self.download_youtube_video(youtube_url, update)
            
            # Format duration as minutes:seconds
            minutes = int(video_data['duration'] / 60)
            seconds = video_data['duration'] % 60
            duration_str = f"{minutes}:{seconds:02d}"
            
            # Format upload date if available
            upload_date_str = ""
            if video_data['upload_date']:
                try:
                    upload_date = datetime.strptime(video_data['upload_date'], '%Y%m%d')
                    upload_date_str = upload_date.strftime('%Y-%m-%d')
                except:
                    upload_date_str = video_data['upload_date']
            
            # Format view count with thousands separator
            views_str = f"{video_data['views']:,}" if video_data['views'] else "Unknown"
            
            # Use YouTube title if no custom title is provided
            title_to_use = custom_title if custom_title else video_data['title']
            
            # Check if paused before uploading
            if not pause_event.is_set():
                await download_message.edit_text(
                    f"⏸️ <b>Upload process is paused.</b> Downloaded video will be uploaded when resumed.",
                    parse_mode='HTML'
                )
                # Wait until resumed
                pause_event.wait()
            
            # Update message to show uploading
            upload_emoji = random_emoji(UPLOAD_EMOJIS)
            await download_message.edit_text(
                f"{upload_emoji} <b>Uploading to Facebook...</b>",
                parse_mode='HTML'
            )
            
            # Upload to Facebook with the title
            post_id = await self.upload_to_facebook(video_data['path'], title_to_use, update)
            
            # Clean up
            if os.path.exists(video_data['path']):
                os.remove(video_data['path'])
                logger.info(f"Deleted temporary file: {video_data['path']}")
            
            # Create link to Facebook post
            facebook_url = f"https://www.facebook.com/{post_id}"
            
            # Create inline keyboard with link to post
            keyboard = [
                [InlineKeyboardButton("📱 View on Facebook", url=facebook_url)],
                [InlineKeyboardButton("🔄 Process Another Video", callback_data="process_another")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Random success emoji
            success_emoji = random_emoji(SUCCESS_EMOJIS)
            
            # Update to success message
            await download_message.edit_text(
                f"{success_emoji} <b>UPLOAD SUCCESSFUL!</b>\n\n"
                f"🎬 <b>Title:</b> {title_to_use}\n"
                f"📱 <b>Platform:</b> Facebook\n"
                f"⏱️ <b>Duration:</b> {duration_str}\n"
                f"👤 <b>Channel:</b> {video_data['channel']}\n"
                f"🆔 <b>Post ID:</b> <code>{post_id}</code>\n\n"
                f"✨ <b>Completed at:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
            # Delete the success message after 10 seconds
            await asyncio.sleep(10)
            try:
                await download_message.delete()
            except Exception as e:
                logger.error(f"Error deleting success message: {str(e)}")
            
            return post_id
            
        except Exception as e:
            await update.message.reply_text(f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')
            return None

    async def process_videos_from_file(self, update: Update):
        """Process videos from file in reverse order and remove each URL after processing"""
        try:
            if not os.path.exists('videos.txt'):
                await update.message.reply_text("❌ <b>Error:</b> videos.txt file not found!", parse_mode='HTML')
                return

            # Create a file path for backup
            backup_file = 'videos_backup.txt'
            
            # Create a backup of the original file
            try:
                with open('videos.txt', 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
                logger.info(f"Created backup file: {backup_file}")
            except Exception as e:
                logger.error(f"Error creating backup file: {str(e)}")

            # Read all lines from the file
            with open('videos.txt', 'r', encoding='utf-8') as file:
                lines = [line.strip() for line in file if line.strip() and not line.startswith('#')]
                lines.reverse()
            
            total_videos = len(lines)
            completed_videos = 0
            
            if total_videos == 0:
                await update.message.reply_text("❌ <b>No videos found in videos.txt!</b>", parse_mode='HTML')
                return
            
            # Create stylish progress bar
            progress_bar = "■□□□□□□□□□"
            
            # Create comprehensive status message - simpler now
            status_message = await update.message.reply_text(
                f"📊 <b>UPLOAD QUEUE</b>\n\n"
                f"<b>Videos found:</b> {total_videos}\n"
                f"<b>Status:</b> Starting...",
                parse_mode='HTML'
            )
            
            # Store status message for pause/resume functionality
            self.status_message = status_message

            # Process each video
            for i, line in enumerate(lines, 1):
                # Check if the process is paused
                global pause_event, skip_requested
                if not pause_event.is_set():
                    pause_msg = await update.message.reply_text(
                        f"⏸️ <b>Upload process is paused.</b> Use /resume to continue.",
                        parse_mode='HTML'
                    )
                    # Wait until resumed
                    pause_event.wait()
                    # Delete the pause message when resumed
                    await pause_msg.delete()
                
                # Extract YouTube URL
                youtube_url = self.extract_youtube_url(line)
                if not youtube_url:
                    continue
                    
                # Extract title from the line (everything before the URL)
                current_title = line.split('https://')[0].strip() or "Untitled video"
                
                # Update filled progress bar
                filled = int(10 * (i-1) / total_videos)
                progress_bar = "■" * filled + "□" * (10 - filled)
                
                # Update status message with current progress
                await status_message.edit_text(
                    f"📊 <b>PROCESSING VIDEO {i}/{total_videos}</b>\n\n"
                    f"🎬 <b>Current:</b> {current_title[:40]}...\n"
                    f"▪️ <b>Progress:</b> {progress_bar}",
                    parse_mode='HTML'
                )
                
                # Process the video
                post_id = await self.process_video(line, update)
                
                # If successfully processed, remove the line from videos.txt
                if post_id:
                    completed_videos += 1
                    
                    """
                    # Update the videos.txt file to remove the processed URL
                    try:
                        with open('videos.txt', 'r', encoding='utf-8') as file:
                            all_lines = file.readlines()
                        
                        # Find and remove the processed URL
                        with open('videos.txt', 'w', encoding='utf-8') as file:
                            for file_line in all_lines:
                                # Skip only the exact line that contains this URL
                                if youtube_url in file_line and file_line.strip() == line.strip():
                                    logger.info(f"Removed processed video from videos.txt: {line[:40]}...")
                                    continue
                                file.write(file_line)
                            
                    except Exception as e:
                        logger.error(f"Error updating videos.txt: {str(e)}")
                    """
                
                # Wait between uploads with countdown - use asyncio.sleep consistently
                if i < len(lines):
                    wait_emoji = random_emoji(WAITING_EMOJIS)
                    wait_message = await update.message.reply_text(
                        f"⏳ <b>Waiting before next video...</b>\n"
                        f"<i>Countdown: 0h 58m 0s remaining</i>\n"
                        f"<i>Use /skip to skip waiting and /pause to pause uploads</i>",
                        parse_mode='HTML'
                    )
                    
                    # Store wait message for skip functionality
                    self.wait_message = wait_message
                    
                    # Reset skip flag if not already set
                    global skip_requested
                    
                    # Simple wait with skip capability
                    try:
                        # Check if skip was already requested before wait started
                        if skip_requested:
                            await wait_message.edit_text(
                                f"⏭️ <b>Skipping wait time!</b> Moving to next video...",
                                parse_mode='HTML'
                            )
                            await asyncio.sleep(2)  # Show skip message briefly
                        else:
                            # Wait for the specified time or until skip is requested
                            elapsed_time = 0
                            while elapsed_time < self.wait_time and not skip_requested:
                                # Check if paused
                                if not pause_event.is_set():
                                    # Calculate remaining time
                                    remaining = self.wait_time - elapsed_time
                                    hours = remaining // 3600
                                    minutes = (remaining % 3600) // 60
                                    seconds = remaining % 60
                                    
                                    # Show paused message
                                    await wait_message.edit_text(
                                        f"⏸️ <b>Upload process is paused.</b>\n"
                                        f"<i>Countdown paused at {hours}h {minutes}m {seconds}s remaining</i>",
                                        parse_mode='HTML'
                                    )
                                    
                                    # Wait until resumed
                                    while not pause_event.is_set() and not skip_requested:
                                        await asyncio.sleep(1)
                                        # Check if skip was requested during pause
                                        if skip_requested:
                                            break
                                    
                                    # Check if skip was requested during pause
                                    if skip_requested:
                                        await wait_message.edit_text(
                                            f"⏭️ <b>Skipping wait time!</b> Moving to next video...",
                                            parse_mode='HTML'
                                        )
                                        await asyncio.sleep(2)  # Show skip message briefly
                                        break
                                    
                                    # Update message when resumed (if not skipped)
                                    if not skip_requested:
                                        await wait_message.edit_text(
                                            f"⏳ <b>Waiting before next video...</b>\n"
                                            f"<i>Countdown resumed with {hours}h {minutes}m {seconds}s remaining</i>\n"
                                            f"<i>Use /skip to skip waiting and /pause to pause uploads</i>",
                                            parse_mode='HTML'
                                        )
                                
                                # Sleep for 1 second
                                await asyncio.sleep(1)
                                
                                # Only increase time if not paused
                                if pause_event.is_set():
                                    elapsed_time += 1
                                    
                                    # Update countdown every 30 seconds or at the beginning
                                    if elapsed_time % 30 == 0 or elapsed_time <= 5:
                                        # Check if skip was requested during wait
                                        if skip_requested:
                                            break
                                                
                                        # Calculate remaining time
                                        remaining = self.wait_time - elapsed_time
                                        hours = remaining // 3600
                                        minutes = (remaining % 3600) // 60
                                        seconds = remaining % 60
                                        
                                        # Update wait message
                                        await wait_message.edit_text(
                                            f"⏳ <b>Waiting before next video...</b>\n"
                                            f"<i>Countdown: {hours}h {minutes}m {seconds}s remaining</i>\n"
                                            f"<i>Use /skip to skip waiting and /pause to pause uploads</i>",
                                            parse_mode='HTML'
                                        )
                            
                            # Handle skip that happened during the wait loop
                            if skip_requested:
                                await wait_message.edit_text(
                                    f"⏭️ <b>Skipping wait time!</b> Moving to next video...",
                                    parse_mode='HTML'
                                )
                                await asyncio.sleep(2)  # Show skip message briefly
                    except Exception as e:
                        logger.error(f"Error during wait: {str(e)}")
                    finally:
                        # Reset skip flag
                        skip_requested = False
                        
                        # Delete wait message
                        try:
                            await wait_message.delete()
                        except Exception as e:
                            logger.error(f"Error deleting wait message: {str(e)}")
                        
                        # Clear wait message reference
                        self.wait_message = None

            # Delete the status message
            try:
                await status_message.delete()
            except Exception as e:
                logger.error(f"Error deleting status message: {str(e)}")
            
            # Clear status message reference
            self.status_message = None
            
            # Short final success message
            success_emoji = random_emoji(SUCCESS_EMOJIS)
            final_message = await update.message.reply_text(
                f"{success_emoji} <b>All {completed_videos} videos processed!</b>",
                parse_mode='HTML'
            )
            
            # Delete the final message after 10 seconds
            await asyncio.sleep(10)
            try:
                await final_message.delete()
            except Exception as e:
                logger.error(f"Error deleting final message: {str(e)}")
                            
        except Exception as e:
            await update.message.reply_text(f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')
            # Clear status message reference
            self.status_message = None

# Create a global bot instance for commands to use
bot_instance = YouTubeToFacebookBot()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline buttons"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "upload_more" or query.data == "process_another":
        await upload_command(update, context)
    elif query.data == "help":
        await help_command(update, context)
    elif query.data == "start_processing":
        await bot_instance.process_videos_from_file(update.callback_query.message)
    elif query.data == "view_list":
        # Show list of videos to be processed
        try:
            if os.path.exists('videos.txt'):
                with open('videos.txt', 'r', encoding='utf-8') as file:
                    lines = [line.strip() for line in file if line.strip() and not line.startswith('#')]
                    lines.reverse()
                
                video_list = "\n".join([f"{i+1}. {line[:50]}..." for i, line in enumerate(lines)])
                
                await query.message.reply_text(
                    f"📋 <b>VIDEO LIST</b>\n\n"
                    f"{video_list}\n\n"
                    f"<i>Total: {len(lines)} videos</i>",
                    parse_mode='HTML'
                )
            else:
                await query.message.reply_text("❌ <b>Error:</b> videos.txt file not found!", parse_mode='HTML')
        except Exception as e:
            await query.message.reply_text(f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upload command"""
    # Start processing
    await bot_instance.process_videos_from_file(update)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    keyboard = [
        [InlineKeyboardButton("▶️ Start Uploading", callback_data="upload_more")],
        [InlineKeyboardButton("📘 Help & Instructions", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 <b>Welcome to YouTube to Facebook Uploader Bot!</b>\n\n"
        f"<i>This bot helps you download videos from YouTube and upload them to Facebook with just a few clicks.</i>\n\n"
        f"<b>What I can do:</b>\n"
        f"• Download videos from YouTube\n"
        f"• Upload videos to your Facebook page\n"
        f"• Process multiple videos in sequence\n"
        f"• Maintain video quality and metadata\n\n"
        f"<b>Get started by clicking the button below or using these commands:</b>\n"
        f"• /start - Show this welcome message\n"
        f"• /upload - Start processing videos from videos.txt\n"
        f"• /pause - Pause the upload process\n"
        f"• /resume - Resume a paused upload process\n"
        f"• /skip - Skip the current waiting period\n"
        f"• /help - Show detailed help information\n"
        f"• /setwait - Set the wait time between videos\n"
        f"• /setcookies - Set YouTube cookies for authentication\n"
        f"• /upload_cookies - Upload a cookies file\n\n"
        f"<i>Make sure you have added YouTube links in the videos.txt file.</i>\n\n"
        f"<b>🔐 YouTube Authentication:</b>\n"
        f"YouTube sometimes requires authentication to verify you're not a bot.\n"
        f"If you encounter a download error, use /upload_cookies to provide your browser cookies.",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    keyboard = [
        [InlineKeyboardButton("▶️ Start Uploading", callback_data="upload_more")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📖 <b>HELP & INSTRUCTIONS</b>\n\n"
        f"<b>How to use this bot:</b>\n\n"
        f"1️⃣ Create a file named 'videos.txt' in the bot directory\n"
        f"2️⃣ Add YouTube links to the file (one per line)\n"
        f"3️⃣ Use /upload command to start the process\n"
        f"4️⃣ The bot will download each video and upload it to Facebook\n"
        f"5️⃣ You'll receive notifications for each step\n\n"
        f"<b>Format for videos.txt:</b>\n"
        f"<code>Video Title https://www.youtube.com/watch?v=XXXXX</code>\n\n"
        f"<b>Available commands:</b>\n"
        f"• /start - Show welcome message\n"
        f"• /upload - Start processing videos\n"
        f"• /pause - Pause the upload process\n"
        f"• /resume - Resume a paused upload process\n"
        f"• /skip - Skip the current waiting period\n"
        f"• /help - Show this help message\n"
        f"• /setwait - Set the wait time between videos\n"
        f"• /setcookies - Set YouTube cookies for authentication\n"
        f"• /upload_cookies - Upload a cookies file\n\n"
        f"<b>🔐 YouTube Authentication:</b>\n"
        f"If you see the 'Sign in to confirm you're not a bot' error:\n"
        f"1. Log in to YouTube in your web browser\n"
        f"2. Install a browser extension like 'Get cookies.txt' or 'EditThisCookie'\n"
        f"3. Export cookies for youtube.com domain\n"
        f"4. Use /upload_cookies command and send the cookies file\n"
        f"5. Your YouTube session will be saved for future downloads\n\n"
        f"<b>Tips:</b>\n"
        f"• You can add a custom title before the YouTube URL\n"
        f"• Videos are processed from bottom to top of the file\n"
        f"• There's a {bot_instance.wait_time}-second wait between uploads to avoid rate limits\n"
        f"• All actions are logged in 'bot.log' for troubleshooting\n\n"
        f"<i>If you encounter any issues, check the log file for details.</i>",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pause command"""
    global pause_event, is_paused
    if pause_event.is_set():
        # Pause the process
        pause_event.clear()
        is_paused = True
        await update.message.reply_text(
            f"⏸️ <b>Upload process paused.</b> Use /resume to continue.",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"⏸️ Upload process is already paused.",
            parse_mode='HTML'
        )

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resume command"""
    global pause_event, is_paused
    if not pause_event.is_set():
        # Resume the process
        pause_event.set()
        is_paused = False
        await update.message.reply_text(
            f"▶️ <b>Upload process resumed!</b>",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"▶️ Upload process is already running.",
            parse_mode='HTML'
        )

async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /skip command"""
    global skip_requested
    
    # Set skip flag regardless of wait message status
    skip_requested = True
    
    if bot_instance.wait_message is not None:
        await update.message.reply_text(
            f"⏭️ <b>Skipping current wait time!</b> Processing will continue with the next video shortly.",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"⏭️ <b>Skip command received.</b> Will skip wait time when it starts.",
            parse_mode='HTML'
        )

async def callback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback to go back to start"""
    await start_command(update, context)

async def setwait_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setwait command to set the wait time between videos"""
    try:
        # Check if a wait time was provided
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                f"⚠️ <b>Please provide a wait time in seconds.</b>\n"
                f"Example: /setwait 300 (for 5 minutes)",
                parse_mode='HTML'
            )
            return
            
        # Parse the wait time
        wait_time = int(context.args[0])
        if wait_time < 0:
            await update.message.reply_text(
                f"❌ <b>Wait time must be a positive number.</b>",
                parse_mode='HTML'
            )
            return
            
        # Set the wait time in the bot instance
        bot_instance.wait_time = wait_time
        
        # Format the time in a human-readable format
        if wait_time >= 3600:
            hours = wait_time // 3600
            minutes = (wait_time % 3600) // 60
            time_str = f"{hours} hour{'s' if hours > 1 else ''}"
            if minutes > 0:
                time_str += f" and {minutes} minute{'s' if minutes > 1 else ''}"
        elif wait_time >= 60:
            minutes = wait_time // 60
            seconds = wait_time % 60
            time_str = f"{minutes} minute{'s' if minutes > 1 else ''}"
            if seconds > 0:
                time_str += f" and {seconds} second{'s' if seconds > 1 else ''}"
        else:
            time_str = f"{wait_time} second{'s' if wait_time != 1 else ''}"
        
        await update.message.reply_text(
            f"⏱️ <b>Wait time between videos set to {time_str}.</b>",
            parse_mode='HTML'
        )
    except ValueError:
        await update.message.reply_text(
            f"❌ <b>Invalid number format.</b> Please provide a valid number of seconds.",
            parse_mode='HTML'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Error:</b> {str(e)}",
            parse_mode='HTML'
        )

async def set_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setcookies command to save YouTube cookies"""
    # Check if there are any arguments
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            f"⚠️ <b>Please provide a cookies file path or content.</b>\n\n"
            f"<b>To use:</b>\n"
            f"1. You can upload your cookies.txt file using /upload_cookies\n"
            f"2. Or send the raw cookie data with /setcookies [data]\n\n"
            f"<i>To get cookies from your browser:</i>\n"
            f"- Install a cookies manager extension\n"
            f"- Log in to YouTube in your browser\n"
            f"- Export cookies for youtube.com to a .txt file\n"
            f"- Use that file with this command</i>",
            parse_mode='HTML'
        )
        return
    
    try:
        # Join all args to handle spaces in the cookie data
        cookie_data = ' '.join(context.args)
        
        # Write the cookies to a file
        with open(bot_instance.cookies_file, 'w', encoding='utf-8') as f:
            f.write(cookie_data)
        
        await update.message.reply_text(
            f"🍪 <b>Cookies saved successfully!</b>\n\n"
            f"YouTube session is now authenticated. Try downloading videos again.",
            parse_mode='HTML'
        )
        
        # Log the action
        logger.info(f"Cookies saved by user {update.effective_user.username or update.effective_user.id}")
    
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Error saving cookies:</b> {str(e)}",
            parse_mode='HTML'
        )

async def upload_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upload_cookies command to upload a cookies file"""
    await update.message.reply_text(
        f"📤 <b>Please send your cookies.txt file.</b>\n\n"
        f"Reply to this message with the file attachment.",
        parse_mode='HTML'
    )

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming file uploads for cookies"""
    # Check if this is a cookie file
    if update.message.document and (
            update.message.document.file_name.endswith('.txt') or 
            update.message.document.mime_type == 'text/plain'):
        
        try:
            # Download the file
            file = await update.message.document.get_file()
            cookie_file_path = f"temp_{update.message.document.file_name}"
            await file.download_to_drive(cookie_file_path)
            
            # Read the file content
            with open(cookie_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                cookie_content = f.read()
            
            # Check if it seems like a cookie file
            if 'domain' in cookie_content.lower() and '.youtube.com' in cookie_content.lower():
                # Save to the bot's cookie file
                with open(bot_instance.cookies_file, 'w', encoding='utf-8') as f:
                    f.write(cookie_content)
                
                await update.message.reply_text(
                    f"🍪 <b>Cookie file uploaded and saved successfully!</b>\n\n"
                    f"YouTube session is now authenticated. Try downloading videos again.",
                    parse_mode='HTML'
                )
                
                # Log the action
                logger.info(f"Cookie file uploaded by user {update.effective_user.username or update.effective_user.id}")
            else:
                await update.message.reply_text(
                    f"⚠️ <b>The uploaded file doesn't appear to be a valid YouTube cookies file.</b>\n\n"
                    f"Please ensure you're exporting cookies from YouTube domain.",
                    parse_mode='HTML'
                )
            
            # Clean up temp file
            if os.path.exists(cookie_file_path):
                os.remove(cookie_file_path)
        
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Error processing cookie file:</b> {str(e)}",
                parse_mode='HTML'
            )

def main():
    # Create the Application
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Add command handlers
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('upload', upload_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('pause', pause_command))
    app.add_handler(CommandHandler('resume', resume_command))
    app.add_handler(CommandHandler('skip', skip_command))
    app.add_handler(CommandHandler('setwait', setwait_command))
    app.add_handler(CommandHandler('setcookies', set_cookies_command))
    app.add_handler(CommandHandler('upload_cookies', upload_cookies_command))
    
    # Add callback handler for inline buttons
    app.add_handler(CallbackQueryHandler(callback_start, pattern="start"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="help"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Add message handler for file uploads
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))

    # Start the bot
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main() 
