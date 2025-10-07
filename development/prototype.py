import os
import vlc
import yt_dlp
import threading
import time
import queue
import requests
from dotenv import load_dotenv

ENV_FILE = ".env"

# --- ENV KEY HANDLING ---
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


# --- FETCH RECOMMENDATIONS (API) ---
def fetch_related_videos_api(video_id, max_results=5, api_key=None):
    """Fetch related videos using YouTube Data API v3."""
    if not api_key:
        print("⚠ No API key provided for autofill.")
        return []

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "type": "video",
        "relatedToVideoId": video_id,
        "maxResults": max_results,
        "key": api_key
    }

    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("items", []):
            vid = item["id"]["videoId"]
            title = item["snippet"]["title"]
            results.append({"id": vid, "title": title})
        return results
    except requests.exceptions.HTTPError as e:
        print(f"⚠ Error fetching recommendations: {e.response.text}")
    except Exception as e:
        print(f"⚠ Unexpected error: {e}")
    return []


# --- YT-DLP SETTINGS ---
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


# --- MAIN PLAYER CLASS ---
class YouTubePlayer:
    def __init__(self, autofill=0, api_key=None):
        self.q = queue.Queue()
        self.autofill = autofill
        self.player = None
        self.current_video = None
        self.playing = False
        self.api_key = api_key

    def search(self, query, max_results=5):
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return info["entries"]

    def add_to_queue(self, url, title=None):
        self.q.put((url, title))

    def get_audio_url(self, url):
        with yt_dlp.YoutubeDL(INFO_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            return info["url"], info

    def play_next(self):
        if self.q.empty():
            if self.autofill > 0 and self.current_video:
                self.fetch_recommendations()
                if self.q.empty():
                    print("Queue empty. Stopping.")
                    return
            else:
                print("Queue empty. Stopping.")
                return

        url, title = self.q.get()
        stream_url, info = self.get_audio_url(url)
        self.current_video = info
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
                self.play_next()
                break
            time.sleep(1)

    def fetch_recommendations(self):
        """Fetch related videos using YouTube Data API."""
        last_id = self.current_video.get("id")
        if not last_id:
            print("⚠ No video ID available for autofill.")
            return

        print(f"Fetching {self.autofill} recommendations via YouTube API...")
        recs = fetch_related_videos_api(last_id, max_results=self.autofill, api_key=self.api_key)
        if not recs:
            print("⚠ No recommendations found (API returned none).")
            return

        for r in recs:
            vid_url = f"https://www.youtube.com/watch?v={r['id']}"
            title = r["title"]
            print(f" + Autofill added: {title}")
            self.q.put((vid_url, title))

    def pause(self):
        if self.player:
            if self.player.is_playing():
                self.player.pause()
                print("⏸ Paused")
            else:
                self.player.play()
                print("▶ Resumed")

    def skip(self):
        if self.player:
            print("⏭ Skipped")
            self.player.stop()
            self.play_next()

    def show_queue(self):
        if self.q.empty():
            print("Queue is empty.")
        else:
            print("Queue:")
            temp = list(self.q.queue)
            for i, (_, title) in enumerate(temp):
                print(f" {i+1}. {title}")


# --- CLI ---
if __name__ == "__main__":
    api_key = get_api_key()
    player = YouTubePlayer(autofill=5, api_key=api_key)

    print("Commands: search <query>, play, pause, skip, queue, autofill <n>, exit")
    while True:
        cmd = input(">>> ").strip()

        if cmd.startswith("search "):
            query = cmd[len("search "):]
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

        elif cmd == "play":
            player.play_next()

        elif cmd == "pause":
            player.pause()

        elif cmd == "skip":
            player.skip()

        elif cmd == "queue":
            player.show_queue()

        elif cmd.startswith("autofill "):
            try:
                n = int(cmd.split()[1])
                player.autofill = n
                print(f"Autofill set to {n}")
            except:
                print("Invalid number.")

        elif cmd == "exit":
            print("Bye!")
            break

        else:
            print("Unknown command.")

