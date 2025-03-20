from flask import Flask, render_template, request, jsonify
from pytube import Playlist, YouTube
import threading
import queue
import time

app = Flask(__name__)

# Global queue for storing results
result_queue = queue.Queue()

def extract_urls(playlist_url):
    try:
        # Convert to playlist URL if it's a video URL
        if 'watch?v=' in playlist_url:
            playlist_url = playlist_url.replace('watch?v=', 'playlist?list=')
        
        playlist = Playlist(playlist_url)
        total_videos = len(playlist.video_urls)
        
        if total_videos == 0:
            result_queue.put({
                'status': 'error',
                'message': 'No videos found in playlist'
            })
            return
        
        # Get all URLs without checking availability
        urls = playlist.video_urls
        
        # Send final results
        result_queue.put({
            'status': 'complete',
            'urls': urls,
            'total_count': total_videos
        })
        
    except Exception as e:
        result_queue.put({
            'status': 'error',
            'message': str(e)
        })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def start_extraction():
    playlist_url = request.form.get('url', '').strip()
    
    if not playlist_url:
        return jsonify({
            'status': 'error',
            'message': 'Please enter a playlist URL'
        })
    
    # Clear the queue
    while not result_queue.empty():
        result_queue.get()
    
    # Start extraction in a separate thread
    thread = threading.Thread(target=extract_urls, args=(playlist_url,))
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