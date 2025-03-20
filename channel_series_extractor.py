from flask import Flask, render_template, request, jsonify
from pytube import Channel, YouTube
import threading
import queue
import re
import time
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# Global queue for storing results
result_queue = queue.Queue()

def get_channel_id_from_url(url):
    """Extract channel ID from various YouTube URL formats"""
    try:
        # Clean the URL
        url = url.strip()
        if not url.startswith('http'):
            url = 'https://' + url
            
        # Handle different URL formats
        if '/channel/' in url:
            return url.split('/channel/')[1].split('/')[0]
        elif '/c/' in url or '/user/' in url or '/@' in url:
            # For custom URLs, we need to get the channel ID from the page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find channel ID in meta tags
            meta_tags = soup.find_all('meta', property='og:url')
            for tag in meta_tags:
                if '/channel/' in tag.get('content', ''):
                    return tag.get('content').split('/channel/')[1].split('/')[0]
            
            # If not found in meta tags, try to find in page content
            channel_id_match = re.search(r'"channelId":"([^"]+)"', response.text)
            if channel_id_match:
                return channel_id_match.group(1)
            
            raise Exception("Could not find channel ID in page content")
        else:
            # Try to get channel ID from the URL
            yt = YouTube(url)
            return yt.channel_id
    except Exception as e:
        raise Exception(f"Could not extract channel ID from URL: {str(e)}")

def extract_series_videos(channel_url, series_name):
    try:
        # Get channel ID from URL
        channel_id = get_channel_id_from_url(channel_url)
        channel_url = f"https://www.youtube.com/channel/{channel_id}"
        
        # Create channel object
        channel = Channel(channel_url)
        videos = []
        
        # Get all videos from channel
        for video in channel.videos:
            title = video.title.lower()
            series_name_lower = series_name.lower()
            
            # Check if video belongs to the series
            if series_name_lower in title:
                # Try to extract episode number
                episode_match = re.search(r'episode\s*(\d+)', title, re.IGNORECASE)
                episode_num = int(episode_match.group(1)) if episode_match else 0
                
                videos.append({
                    'title': video.title,
                    'url': f"https://www.youtube.com/watch?v={video.video_id}",
                    'episode': episode_num
                })
        
        # Sort videos by episode number
        videos.sort(key=lambda x: x['episode'])
        
        # Send results
        result_queue.put({
            'status': 'complete',
            'videos': videos,
            'total_count': len(videos)
        })
        
    except Exception as e:
        result_queue.put({
            'status': 'error',
            'message': str(e)
        })

@app.route('/')
def index():
    return render_template('series_extractor.html')

@app.route('/extract', methods=['POST'])
def start_extraction():
    channel_url = request.form.get('channel_url', '').strip()
    series_name = request.form.get('series_name', '').strip()
    
    if not channel_url or not series_name:
        return jsonify({
            'status': 'error',
            'message': 'Please enter both channel URL and series name'
        })
    
    # Clear the queue
    while not result_queue.empty():
        result_queue.get()
    
    # Start extraction in a separate thread
    thread = threading.Thread(target=extract_series_videos, args=(channel_url, series_name))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'status': 'started',
        'message': 'Extraction started'
    })

@app.route('/status')
def get_status():
    try:
        result = result_queue.get_nowait()
        return jsonify(result)
    except queue.Empty:
        return jsonify({
            'status': 'waiting',
            'message': 'Waiting for results...'
        })

if __name__ == '__main__':
    app.run(debug=True) 