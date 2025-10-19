import os
import vlc
import yt_dlp
import threading
import time
import queue
import random
import requests
from dotenv import load_dotenv

ENV_FILE = ".env"
CACHE_DIR = "cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def get_api_key():
    load_dotenv(ENV_FILE)
    key = os.getenv("YOUTUBE_API_KEY")
    if key:
        return key
    print("⚠ No YouTube Data API key found.")
    key = input("Enter your YouTube Data API key: ").strip()
    if key:
        with open(ENV_FILE, "a") as f:
            f.write(f"\nYOUTUBE_API_KEY={key}\n")
        print("✅ API key saved to .env")
    return key

SEARCH_OPTS = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "default_search": "ytsearch"
}

INFO_OPTS = {
    "quiet": True,
    "skip_download": True,
    "format": "bestaudio/best"
}

class YouTubePlayer:
    def __init__(self, autofill=0, api_key=None):
        self.q = []
        self.played = []
        self.autofill = autofill
        self.player = None
        self.current_video = None
        self.playing = False
        self.api_key = api_key
        self.mode = "normal"  # normal | repeat | repeatone | shuffle
        self.cache = {}

    def search(self, query, max_results=5):
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return info["entries"]

    def add_to_queue(self, url, title=None):
        self.q.append((url, title))

    def get_audio_url(self, url):
        if url in self.cache:
            return self.cache[url]
        with yt_dlp.YoutubeDL(INFO_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info["url"]
            self.cache[url] = (stream_url, info)
            return stream_url, info

    def play(self, index=None):
        if index is not None:
            if 0 <= index < len(self.q):
                url, title = self.q.pop(index)
            else:
                print("Invalid index.")
                return
        elif not self.q:
            print("Queue empty.")
            return
        else:
            url, title = self.q.pop(0)

        stream_url, info = self.get_audio_url(url)
        self.current_video = info
        self.played.append((url, info['title']))
        print(f"▶ Playing: {info['title']}")

        if self.player:
            self.player.stop()

        self.player = vlc.MediaPlayer(stream_url)
        self.player.play()
        self.playing = True

        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self):
        while self.playing:
            if self.player.get_state() == vlc.State.Ended:
                self.playing = False
                print("Song ended.")
                self.next()
                break
            time.sleep(1)

    def next(self):
        if self.mode == "repeatone" and self.current_video:
            url = self.current_video.get("webpage_url")
            title = self.current_video.get("title")
            self.q.insert(0, (url, title))
        elif self.mode == "repeat" and self.current_video:
            url = self.current_video.get("webpage_url")
            title = self.current_video.get("title")
            self.q.append((url, title))
        elif self.mode == "shuffle" and self.q:
            random.shuffle(self.q)
        if self.q:
            self.play()
        else:
            print("Queue empty. Stopping.")

    def pause(self):
        if self.player:
            if self.player.is_playing():
                self.player.pause()
                print("⏸ Paused")
            else:
                self.player.play()
                print("▶ Resumed")

    def show_queue(self):
        if not self.q and not self.played:
            print("Queue is empty.")
            return
        print("\n--- Queue ---")
        for i, (_, title) in enumerate(self.q):
            print(f" {i}. {title}")
        if self.played:
            print("\n--- Played ---")
            for i, (_, title) in enumerate(self.played[-5:]):
                print(f" ✓ {title}")

    def toggle_mode(self, mode):
        self.mode = mode
        print(f"Mode set to: {mode}")

if __name__ == "__main__":
    api_key = get_api_key()
    player = YouTubePlayer(autofill=5, api_key=api_key)

    print("Commands: s <query>, add <url>, p [n], pa, n, q, r, r1, sh, exit")

    while True:
        cmd = input(">>> ").strip().split()
        if not cmd:
            continue

        main = cmd[0]
        args = cmd[1:]

        if main == "s":
            query = " ".join(args)
            results = player.search(query)
            for i, r in enumerate(results):
                print(f"[{i}] {r['title']}")
            choice = input("Choose index (or many with space): ").split()
            for c in choice:
                if c.isdigit():
                    idx = int(c)
                    url = results[idx]["url"]
                    title = results[idx]["title"]
                    player.add_to_queue(url, title)
                    print(f" + Added: {title}")

        elif main == "add" and args:
            url = args[0]
            player.add_to_queue(url, url)
            print(f" + Added link: {url}")

        elif main == "p":
            idx = int(args[0]) if args else None
            player.play(idx)

        elif main == "pa":
            player.pause()

        elif main == "n":
            player.next()

        elif main == "q":
            player.show_queue()

        elif main == "r":
            player.toggle_mode("repeat")

        elif main == "r1":
            player.toggle_mode("repeatone")

        elif main == "sh":
            player.toggle_mode("shuffle")

        elif main == "exit":
            print("Bye!")
            break

        else:
            print("Unknown command.")

