import vlc
import yt_dlp
import threading
import time
import queue

SEARCH_OPTS = {
    'quiet': True,
    'skip_download': True,
    'extract_flat': 'in_playlist',
    'default_search': 'ytsearch'
}

INFO_OPTS = {
    'quiet': True,
    'skip_download': True,
    'format': 'bestaudio/best'
}

class YouTubePlayer:
    def __init__(self, autofill=0):
        self.q = queue.Queue()
        self.autofill = autofill
        self.player = None
        self.current_video = None
        self.playing = False

    def search(self, query, max_results=5):
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return info['entries']

    def add_to_queue(self, url, title=None):
        self.q.put((url, title))

    def get_audio_url(self, url):
        with yt_dlp.YoutubeDL(INFO_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            return info['url'], info

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
            state = self.player.get_state()
            if state == vlc.State.Ended:
                self.playing = False
                print("Song ended.")
                self.play_next()
                break
            time.sleep(1)

    def fetch_recommendations(self):
        """Fetch related videos of last played"""
        last_url = f"https://www.youtube.com/watch?v={self.current_video['id']}"
        with yt_dlp.YoutubeDL(INFO_OPTS) as ydl:
            info = ydl.extract_info(last_url, download=False)
            recs = info.get('related_videos', [])
            if not recs:
                print("⚠ No recommendations found.")
                return
            for r in recs[:self.autofill]:
                vid_id = r.get('id')
                if vid_id:
                    vid_url = f"https://www.youtube.com/watch?v={vid_id}"
                    title = r.get('title')
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
    player = YouTubePlayer(autofill=5)

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
                    url = results[idx]['url']
                    title = results[idx]['title']
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
