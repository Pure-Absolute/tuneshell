import os
import vlc
import yt_dlp
import threading
import random
import json
from dotenv import load_dotenv
import time

# ---------------------- CONFIG ----------------------
ENV_FILE = ".env"
PLAYLIST_DIR = "playlist"
DOWNLOAD_DIR = "downloads"
CACHE_DIR = "cache"  # for streaming url cache (not file cache)
DOWNLOAD_INDEX = os.path.join(DOWNLOAD_DIR, "index.json")

# ensure folders
for d in (PLAYLIST_DIR, DOWNLOAD_DIR, CACHE_DIR):
    os.makedirs(d, exist_ok=True)

# ---------------------- YT-DLP OPTIONS ----------------------
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

DOWNLOAD_OPTS_BASE = {
    "quiet": True,
    "format": "bestaudio/best",
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
}

# ---------------------- UTILITIES ----------------------

def get_api_key():
    load_dotenv(ENV_FILE)
    key = os.getenv("YOUTUBE_API_KEY")
    if key:
        return key
    print("⚠ No YouTube Data API key found.")
    key = input("Enter your YouTube Data API key: ").strip()
    if key:
        with open(ENV_FILE, "a") as f:
            f.write(f"\nYOUTUBE_API_KEY={key}\n") # Add newlines
        print("✅ API key saved to .env")
    return key


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error reading {path}. File might be corrupt. Creating backup.")
        os.rename(path, f"{path}.bak")
        return None


# ---------------------- DOWNLOAD INDEX ----------------------

download_index = load_json(DOWNLOAD_INDEX) or {}


def save_download_index():
    save_json(DOWNLOAD_INDEX, download_index)


# ---------------------- PLAYER CLASS ----------------------
class YouTubePlayer:
    def __init__(self, autofill=0, api_key=None):
        self.q = []  # list of (id_or_url, title, is_offline)
        self.played = []  # list of (id_or_url, title, is_offline)
        self.autofill = autofill
        self.player = None
        self.current = None  # info dict
        self.playing = False
        self.api_key = api_key
        self.mode = "normal"  # normal | repeat | repeatone | shuffle
        self.cache = {}  # url -> (stream_url, info)
        self.volume = 60
        self._lock = threading.RLock() # Use RLock for nested locks
        self._vlc_instance = vlc.Instance() # Use a single instance

    # ---------- yt-dlp helpers ----------
    def search(self, query, max_results=5):
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return info.get("entries", [])

    def extract_info(self, url_or_id):
        with yt_dlp.YoutubeDL(INFO_OPTS) as ydl:
            return ydl.extract_info(url_or_id, download=False)

    def is_playlist_url(self, url):
        return "list=" in url or "playlist?list=" in url

    def add_youtube_playlist(self, url):
        # FIX 1: Apply robust URL parsing
        opts = {"quiet": True, "skip_download": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            entries = data.get("entries", [])
            count = 0
            for e in entries:
                vid_or_url = e.get("url") or e.get("id")
                title = e.get("title")
                
                full_url = None
                if vid_or_url and (vid_or_url.startswith('http://') or vid_or_url.startswith('https://')):
                    full_url = vid_or_url # It's already a full URL
                elif vid_or_url:
                    full_url = f"https://www.youtube.com/watch?v={vid_or_url}" # It's just an ID
                else:
                    continue # Skip if no ID or URL

                self.q.append((full_url, title, False))
                count += 1
            print(f" + Added {count} videos from playlist")

    def get_stream(self, url):
        # This is a blocking I/O call
        if url in self.cache:
            stream_url, info = self.cache[url]
            # Simple check if URL might be expired (basic, not perfect)
            if 'expire' in stream_url:
                 # TODO: Check expiration timestamp if available
                 pass # Assume it's okay for now, VLC will handle it
            return self.cache[url]
            
        with yt_dlp.YoutubeDL(INFO_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get("url")
            self.cache[url] = (stream_url, info)
            return stream_url, info

    # ---------- playback core ----------
    def _start_player(self, stream_url):
        # This function MUST be called with the lock held
        if self.player:
            try:
                events = self.player.event_manager()
                events.event_detach(vlc.EventType.MediaPlayerEndReached)
                if self.player.is_playing():
                    self.player.stop()
            except Exception as e:
                print(f"Error stopping old player: {e}")
                pass # Continue anyway
        
        self.player = self._vlc_instance.media_player_new()
        media = self._vlc_instance.media_new(stream_url)
        self.player.set_media(media)
        
        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self.handle_end_reached)
        
        self.player.audio_set_volume(self.volume)
        self.player.play()
        self.playing = True

    def handle_end_reached(self, event):
        # This callback runs in a separate thread (from VLC)
        with self._lock:
            # We call the internal logic which is also locked
            # This is safe because it's an RLock
            self._stop_and_next_logic()

    def play_index(self, index=None):
        # This function is now designed to release the lock
        # during slow I/O (get_stream).

        url, title, is_offline = None, None, None
        hist_item = None
        
        with self._lock:
            # --- 1. Get item from queue (inside lock) ---
            if index is not None and index < 0:
                neg = -index
                if neg <= len(self.played):
                    hist_item = self.played[-neg]
                    url, title, is_offline = hist_item
                else:
                    print("Invalid negative index.")
                    print(self.status_line(), end="", flush=True) # FIX 2: Re-print prompt
                    return
            elif index is None:
                if not self.q:
                    print("Queue empty.")
                    self.current = None
                    self.playing = False
                    print(self.status_line(), end="", flush=True) # FIX 2: Re-print prompt
                    return
                url, title, is_offline = self.q.pop(0)
            else:
                if index < 0 or index >= len(self.q):
                    print("Invalid index.")
                    print(self.status_line(), end="", flush=True) # FIX 2: Re-print prompt
                    return
                url, title, is_offline = self.q.pop(index)

        # --- 2. Perform slow I/O (outside lock) ---
        stream_url_or_path = None
        info_dict = None
        try:
            if is_offline:
                path = download_index.get(url, {}).get("path")
                if not path or not os.path.exists(path):
                    print(f"Offline file not found for {title} ({url})")
                    # Try to play next item if current fails
                    self.play_index() 
                    return
                stream_url_or_path = path
                info_dict = {"title": title, "id": url, "webpage_url": url}
            else:
                # This is the slow network call
                stream_url, info = self.get_stream(url)
                stream_url_or_path = stream_url
                info_dict = info
        except Exception as e:
            print(f"Error getting stream for {title}: {e}")
            # Try next song automatically if this one fails
            self.play_index() 
            return

        # --- 3. Update state and start player (inside lock) ---
        with self._lock:
            self.current = info_dict
            if is_offline:
                print(f"▶ Playing (offline): {info_dict.get('title')}")
            else:
                print(f"▶ Playing: {info_dict.get('title')}")
            
            self._start_player(stream_url_or_path)

            # Add to played list
            if hist_item:
                # It was a history item, don't re-add
                pass
            else:
                self.played.append((url, title or (self.current or {}).get('title', '<unknown>'), is_offline))
                # Keep history trimmed
                if len(self.played) > 50:
                    self.played = self.played[-50:]
            
            # FIX 2: Re-print prompt after *any* successful play
            print(self.status_line(), end="", flush=True)


    def toggle_play_pause(self, index=None):
        with self._lock:
            if index is not None:
                try:
                    idx = int(index)
                except ValueError:
                    print("Invalid index")
                    print(self.status_line(), end="", flush=True) # FIX 2: Re-print
                    return
                # Stop current player before playing new index
                if self.player and self.player.is_playing():
                    self.player.stop()
                self.play_index(idx) # Handles its own prompt
                return # IMPORTANT

            if not self.player:
                self.play_index() # Handles its own prompt
                return # IMPORTANT
            
            # Need to check state properly
            state = self.player.get_state()
            if state == vlc.State.Playing:
                self.player.pause()
                print("⏸ Paused")
                self.playing = False
            elif state == vlc.State.Paused:
                self.player.play()
                print("▶ Resumed")
                self.playing = True
            elif state == vlc.State.Ended or state == vlc.State.Stopped or state == vlc.State.Error:
                # If player is stopped/ended, "p" should play from queue
                print("Player stopped. Playing next from queue...")
                self.play_index() # Handles its own prompt
                return # IMPORTANT
            else:
                # Buffering, Opening, etc.
                print(f"Player state: {state}. Waiting...")
                time.sleep(0.1)
                if self.player.is_playing():
                     self.player.pause()
                     print("⏸ Paused")
                     self.playing = False
                else:
                     # Fallback to play if it's in a weird state
                     self.player.play()
                     print("▶ Resumed")
                     self.playing = True

            # FIX 2: Only paths that don't call play_index will reach here.
            print(self.status_line(), end="", flush=True)


    def _stop_and_next_logic(self):
        # Internal function that assumes lock is already held
        print("\n[Track Finished] Playing next...")
        if self.player:
            try:
                if self.player.is_playing() or self.player.get_state() == vlc.State.Paused:
                     self.player.stop()
            except Exception:
                pass
            self.playing = False
        
        # Check if current exists
        current_is_offline = False
        if self.current:
            current_id = self.current.get('id') or self.current.get('webpage_url')
            # Check if it's an offline ID
            if current_id in download_index:
                current_is_offline = True
            # Check if it's a URL corresponding to an offline ID
            else:
                for off_id, meta in download_index.items():
                    if meta.get('path') == current_id:
                        current_is_offline = True
                        current_id = off_id # Use the offline ID
                        break

        if self.mode == "repeatone" and self.current:
            curid = self.current.get('id') or self.current.get('webpage_url')
            if current_is_offline:
                 curid = self.current.get('id') # Ensure we use the offline ID
            title = self.current.get('title')
            self.q.insert(0, (curid, title, current_is_offline))
        elif self.mode == "repeat" and self.current:
            curid = self.current.get('id') or self.current.get('webpage_url')
            if current_is_offline:
                 curid = self.current.get('id') # Ensure we use the offline ID
            title = self.current.get('title')
            self.q.append((curid, title, current_is_offline))
        
        if self.mode == "shuffle" and self.q:
            random.shuffle(self.q)
            
        if self.q:
            self.play_index() # Will handle re-printing prompt
        else:
            print("Queue empty. Stopping.")
            self.current = None
            self.playing = False
            # FIX 2: Re-print prompt if queue is empty
            print(self.status_line(), end="", flush=True) 

    def stop_and_next(self):
        with self._lock:
            self._stop_and_next_logic()

    def set_volume(self, v):
        try:
            v = int(v)
        except Exception:
            print("Invalid volume")
            return
        v = max(0, min(100, v))
        self.volume = v
        if self.player:
            try:
                self.player.audio_set_volume(self.volume)
            except Exception:
                pass
        print(f"Volume: {self.volume}%")

    def change_volume(self, delta):
        self.set_volume(self.volume + delta)

    def show_queue(self):
        print("\n--- QUEUE ---")
        if not self.q:
            print("(empty)")
        else:
            for i, (url, title, is_offline) in enumerate(self.q):
                tag = "(offline)" if is_offline else ""
                print(f" {i}. {title} {tag}")
        print("\n--- PLAYED (neg index) ---")
        
        if not self.played:
            print("(none)")
        else:
            played_to_show = self.played[-10:]
            for i, (url, title, is_offline) in enumerate(reversed(played_to_show), start=1):
                tag = "(offline)" if is_offline else ""
                print(f" -{i}: {title} {tag}")
        print("")

    def toggle_mode(self, mode):
        if mode == "repeat":
            self.mode = "repeat" if self.mode != "repeat" else "normal"
        elif mode == "repeatone":
            self.mode = "repeatone" if self.mode != "repeatone" else "normal"
        elif mode == "shuffle":
            self.mode = "shuffle" if self.mode != "shuffle" else "normal"
        print(f"Mode: {self.mode}")

    # ---------- playlist save/load ----------
    def save_playlist(self, name):
        data = []
        for url, title, is_offline in self.q:
            vid = None
            if is_offline:
                vid = url # This is the offline ID
            else:
                if "watch?v=" in url:
                    vid = url.split("watch?v=")[-1].split("&")[0]
                else:
                    vid = url # Fallback
            data.append({"title": title, "id": vid, "offline": is_offline})
        path = os.path.join(PLAYLIST_DIR, f"{name}.json")
        save_json(path, data)
        print(f"Saved playlist: {path}")

    def load_playlist(self, name):
        path = os.path.join(PLAYLIST_DIR, f"{name}.json")
        p = load_json(path)
        if not p:
            print("Playlist not found.")
            return
        count = 0
        for item in p:
            id_ = item.get('id')
            title = item.get('title')
            offline = item.get('offline', False)
            if offline:
                if id_ in download_index:
                    self.q.append((id_, title, True))
                    count += 1
                else:
                    print(f"Skipping missing offline track: {title} ({id_})")
            else:
                full = f"https://www.youtube.com/watch?v={id_}"
                self.q.append((full, title, False))
                count += 1
        print(f"Loaded {count} items from playlist")

    # ---------- download / offline ----------
    def _make_offline_id(self, vid):
        if vid not in download_index:
            return vid
        i = 2
        while True:
            candidate = f"{vid}_{i}"
            if candidate not in download_index:
                return candidate
            i += 1

    def download(self, query_or_url, as_mp3=False):
        opts = dict(DOWNLOAD_OPTS_BASE)
        if as_mp3:
            opts['format'] = 'bestaudio'
            opts.update({
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                # outtmpl is already set in base, but FFmpegExtractAudio needs ext
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
                'postprocessor_args': {
                    # 'ffmpeg': ['-acodec', 'libmp3lame'] # This can be problematic
                }
            })
            # Ensure the final extension is mp3
            opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, '%(id)s') # Let it add .mp3
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = None
            try:
                info = ydl.extract_info(query_or_url, download=True)
            except Exception as e:
                print(f"Download failed: {e}")
                return
            
            if info.get('_type') == 'playlist':
                download_count = 0
                for e in info.get('entries', []):
                    if not e: continue 
                    vid = e.get('id')
                    
                    # yt-dlp 
                    ext = 'mp3' if as_mp3 else e.get('ext') or 'm4a'
                    # Base filename from downloader
                    base_filename = ydl.prepare_filename(e)
                    
                    if as_mp3:
                        # After postprocessing, the file should be .mp3
                        base_filename = os.path.splitext(base_filename)[0] + ".mp3"
                        ext = 'mp3'

                    if not os.path.exists(base_filename):
                         print(f"Warning: File not found for {e.get('title')}: {base_filename}")
                         # Try original ext just in case
                         orig_ext = e.get('ext') or 'm4a'
                         orig_file = os.path.splitext(base_filename)[0] + f".{orig_ext}"
                         if os.path.exists(orig_file):
                            print(f"Found {orig_file} instead. Please check ffmpeg.")
                            base_filename = orig_file
                            ext = orig_ext
                         else:
                             continue

                    offline_id = self._make_offline_id(vid)
                    final_filename = base_filename
                    
                    if offline_id != vid:
                        newname = os.path.join(DOWNLOAD_DIR, f"{offline_id}.{ext}")
                        try:
                            os.rename(base_filename, newname)
                            final_filename = newname
                        except OSError as oe:
                            print(f"Could not rename file {base_filename}: {oe}")
                            continue

                    download_index[offline_id] = {"title": e.get('title'), "path": final_filename}
                    download_count += 1
                save_download_index()
                print(f"Downloaded {download_count} videos to offline folder")
                return
            
            # single video
            vid = info.get('id')
            filename = ydl.prepare_filename(info)

            if as_mp3:
                filename = os.path.splitext(filename)[0] + ".mp3"
                ext = 'mp3'
            else:
                ext = info.get('ext') or 'm4a'


            if not os.path.exists(filename):
                print(f"Error: Downloaded file not found at {filename}")
                return

            offline_id = self._make_offline_id(vid)
            
            if offline_id != vid:
                newname = os.path.join(DOWNLOAD_DIR, f"{offline_id}.{ext}")
                try:
                    os.rename(filename, newname)
                    filename = newname
                except OSError as oe:
                    print(f"Could not rename file {filename}: {oe}")
                    return

            download_index[offline_id] = {"title": info.get('title'), "path": filename}
            save_download_index()
            print(f"Downloaded and indexed as: {offline_id}")

    # ---------- helpers ----------
    def add_offline_by_id(self, offline_id):
        meta = download_index.get(offline_id)
        if not meta:
            print("Offline ID not found.")
            return
        self.q.append((offline_id, meta.get('title'), True))
        print(f" + Added offline: {meta.get('title')} ({offline_id})")

    def add_link(self, link):
        if self.is_playlist_url(link):
            print("Adding playlist...")
            self.add_youtube_playlist(link)
            return
        try:
            print("Getting info...")
            info = self.extract_info(link)
            title = info.get('title')
            full = info.get('webpage_url') or link
            self.q.append((full, title, False))
            print(f" + Added link: {title}")
        except Exception as e:
            print(f"Could not add link: {e}")

    def add_search_result(self, query):
        print(f"Searching for: {query}...")
        results = self.search(query, max_results=5)
        if not results:
            print("No search results.")
            return
        for i, r in enumerate(results):
            print(f"[{i}] {r.get('title')}")
        choice = input("Choose index (or many with space): ").split()
        for c in choice:
            if c.isdigit():
                idx = int(c)
                if 0 <= idx < len(results):
                    url = results[idx].get('url')
                    title = results[idx].get('title')
                    webpage_url = results[idx].get('webpage_url')

                    full = webpage_url # Prefer webpage_url
                    if not full:
                        if url and (url.startswith('http://') or url.startswith('https://')):
                            full = url # url is already a full url
                        else:
                            full = f"https://www.youtube.com/watch?v={url}" # url is just an id
                    
                    self.q.append((full, title, False))
                    print(f" + Added: {title}")

    def status_line(self):
        # symbols: ▶ ⏸ 🔁 🔂 🎲
        with self._lock: # Need lock to safely check player state
            play_sym = '—'
            if self.player:
                 state = self.player.get_state()
                 if state == vlc.State.Playing:
                     play_sym = '▶'
                 elif state == vlc.State.Paused:
                     play_sym = '⏸'
                 elif state == vlc.State.Ended or state == vlc.State.Stopped or state == vlc.State.Error:
                     play_sym = '■' # Stopped/Ended
                 else:
                     play_sym = '…' # Buffering/Opening
            else:
                play_sym = '—'

            mode_sym = '—'
            if self.mode == 'repeat':
                mode_sym = '🔁'
            elif self.mode == 'repeatone':
                mode_sym = '🔂'
            elif self.mode == 'shuffle':
                mode_sym = '🎲'
            vol = f"{self.volume}%"
            now = (self.current.get('title') if self.current else '—')
            
            # Truncate long titles
            if len(now) > 60:
                now = now[:57] + "..."
                
            # \r to reset line, \033[K to clear it
            return f"\r\033[K[{play_sym} {vol} {mode_sym}] {now} >>> "


# ---------------------- CLI ----------------------
if __name__ == '__main__':
    api_key = get_api_key()
    player = YouTubePlayer(autofill=5, api_key=api_key)

    def prompt():
        try:
            # Print the status line, but don't add a newline
            print(player.status_line(), end="", flush=True)
            return input().strip()
        except EOFError:
            return 'exit'

    print("Commands: s <query>, add <url|id>, p [n], v <0-100>|v+|v-, n (next), q, save <name>, load <name>, d <url|query> [-mp3], r, r1, sh, exit/x")

    try:
        # FIX 2: Print the very first prompt
        print(player.status_line(), end="", flush=True)
        while True:
            # Note: prompt() is now only responsible for input()
            # The prompt string is printed either at the end of
            # the last command, or here at the start.
            try:
                raw = input().strip()
            except EOFError:
                raw = 'exit'
            except KeyboardInterrupt:
                # Handle Ctrl+C at the prompt
                print("\nCaught Ctrl+C, type 'exit' or 'x' to quit.")
                print(player.status_line(), end="", flush=True)
                continue
                
            if not raw:
                # User just hit enter, re-print prompt
                print(player.status_line(), end="", flush=True)
                continue
            
            # All commands below are responsible for their own
            # output, but *not* for re-printing the prompt.
            # The functions they call (play_index, etc.) will
            # print the prompt if they are asynchronous.
            # Otherwise, the loop will finish and print()
            # at the end of the loop.

            parts = raw.split()
            cmd = parts[0]
            args = parts[1:]
            
            # Flag to check if a function that prints its
            # own prompt was called
            prompt_will_be_reprinted = False

            if cmd == 's':
                if not args:
                    print("Usage: s <query>")
                else:
                    query = ' '.join(args)
                    player.add_search_result(query)
                    with player._lock: # Check playing status safely
                        if not player.playing and player.q:
                            player.play_index()
                            prompt_will_be_reprinted = True

            elif cmd == 'add' and args:
                target = ' '.join(args) 
                if target in download_index:
                    player.add_offline_by_id(target)
                elif target.startswith('http'):
                    player.add_link(target)
                else:
                    full = f"https://www.youtube.com/watch?v={target}"
                    player.add_link(full)
                with player._lock:
                    if not player.playing and player.q:
                        player.play_index()
                        prompt_will_be_reprinted = True

            elif cmd == 'p':
                player.toggle_play_pause(args[0] if args else None)
                prompt_will_be_reprinted = True # toggle_play_pause always reprints

            elif cmd == 'v':
                if not args:
                    print(f"Volume: {player.volume}%")
                else:
                    a = args[0]
                    if a == 'v+' or a == '+':
                        player.change_volume(10)
                    elif a == 'v-' or a == '-':
                        player.change_volume(-10)
                    else:
                        player.set_volume(a)

            elif cmd == 'v+' or raw == '+':
                player.change_volume(10)
            elif cmd == 'v-' or raw == '-':
                player.change_volume(-10)

            elif cmd == 'n':
                player.stop_and_next()
                prompt_will_be_reprinted = True # stop_and_next always reprints

            elif cmd == 'q':
                player.show_queue()

            elif cmd == 'save' and args:
                player.save_playlist(args[0])

            elif cmd == 'load' and args:
                player.load_playlist(args[0])
                with player._lock:
                    if not player.playing and player.q:
                        player.play_index()
                        prompt_will_be_reprinted = True

            elif cmd == 'd' and args:
                as_mp3 = False
                if '-mp3' in args:
                    as_mp3 = True
                    args = [a for a in args if a != '-mp3']
                target = ' '.join(args)
                if not target:
                    print("Usage: d <url|query> [-mp3]")
                else:
                    player.download(target, as_mp3=as_mp3)

            elif cmd == 'r':
                player.toggle_mode('repeat')

            elif cmd == 'r1':
                player.toggle_mode('repeatone')

            elif cmd == 'sh':
                player.toggle_mode('shuffle')

            elif cmd == 'exit' or cmd == 'x':
                print('Bye!')
                if player.player:
                    player.player.stop()
                break

            else:
                print(f"Unknown command: '{cmd}'")

            # FIX 2: If no async/prompt-printing func was called,
            # re-print the prompt manually.
            if not prompt_will_be_reprinted:
                print(player.status_line(), end="", flush=True)

    except KeyboardInterrupt:
        # This catches Ctrl+C during a blocking call like download
        print("\nBye! (Ctrl+C)")
        if player.player:
            player.player.stop()
    finally:
        # General cleanup
        if player.player:
            player.player.stop()
        # Ensure index is saved on abrupt exit
        save_download_index()



