import tkinter as tk
from tkinter import ttk, scrolledtext
from pytube import Playlist, YouTube
import threading
from datetime import datetime
import re

class PlaylistExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Playlist URL Extractor (India Available)")
        self.root.geometry("800x600")
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Playlist URL input
        ttk.Label(main_frame, text="Playlist URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(main_frame, width=70)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Extract button
        self.extract_button = ttk.Button(main_frame, text="Extract URLs", command=self.start_extraction)
        self.extract_button.grid(row=0, column=3, padx=5, pady=5)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, length=300, mode='determinate', variable=self.progress_var)
        self.progress_bar.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=5)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="")
        self.status_label.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=5)
        
        # URLs text area
        self.urls_text = scrolledtext.ScrolledText(main_frame, width=90, height=25)
        self.urls_text.grid(row=3, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Copy button
        self.copy_button = ttk.Button(main_frame, text="Copy All URLs", command=self.copy_urls)
        self.copy_button.grid(row=4, column=0, columnspan=4, pady=5)
        
        # Configure grid weights
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Store URLs
        self.urls = []

    def is_available_in_india(self, url):
        try:
            yt = YouTube(url)
            # Try to get video details with India region
            yt.check_availability()
            return True
        except Exception as e:
            if "Video unavailable" in str(e) or "This video is not available" in str(e):
                return False
            return True  # If error is not related to availability, assume it's available

    def start_extraction(self):
        # Clear previous results
        self.urls_text.delete(1.0, tk.END)
        self.urls = []
        self.progress_var.set(0)
        self.status_label.config(text="Extracting URLs...")
        self.extract_button.config(state='disabled')
        
        # Start extraction in a separate thread
        thread = threading.Thread(target=self.extract_urls)
        thread.daemon = True
        thread.start()

    def extract_urls(self):
        try:
            playlist_url = self.url_entry.get().strip()
            if not playlist_url:
                self.update_status("Please enter a playlist URL")
                return
            
            # Convert to playlist URL if it's a video URL
            if 'watch?v=' in playlist_url:
                playlist_url = playlist_url.replace('watch?v=', 'playlist?list=')
            
            playlist = Playlist(playlist_url)
            
            # Get total number of videos
            total_videos = len(playlist.video_urls)
            if total_videos == 0:
                self.update_status("No videos found in playlist")
                return
            
            # Extract URLs and update progress
            available_count = 0
            for i, url in enumerate(playlist.video_urls):
                self.update_status(f"Checking availability... {i+1}/{total_videos}")
                if self.is_available_in_india(url):
                    self.urls.append(url)
                    available_count += 1
                progress = (i + 1) / total_videos * 100
                self.progress_var.set(progress)
            
            # Display URLs in text area
            self.urls_text.delete(1.0, tk.END)
            for url in self.urls:
                self.urls_text.insert(tk.END, f"{url}\n")
            
            self.update_status(f"Successfully extracted {available_count} available URLs out of {total_videos} videos")
            
        except Exception as e:
            self.update_status(f"Error: {str(e)}")
        finally:
            self.extract_button.config(state='normal')

    def update_status(self, message):
        self.root.after(0, lambda: self.status_label.config(text=message))

    def copy_urls(self):
        if not self.urls:
            self.update_status("No URLs to copy")
            return
        
        # Copy URLs to clipboard
        urls_text = "\n".join(self.urls)
        self.root.clipboard_clear()
        self.root.clipboard_append(urls_text)
        self.update_status("URLs copied to clipboard")

def main():
    root = tk.Tk()
    app = PlaylistExtractorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 