import os
import subprocess
import threading
import queue
import yt_dlp
import random
import time

# Queue untuk list lagu
playlist = []
index = 0
mpv_proc = None
repeat_mode = None  # None, 'playlist', 'one'

# Lock biar aman
lock = threading.Lock()

def get_audio_url(yt_url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'ytsearch',
        'noplaylist': True,
        'skip_download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(yt_url, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        return info['url'], info.get('title', 'Unknown')

def play_current():
    global mpv_proc, index
    if not playlist:
        print("🎵 Queue kosong.")
        return
    url, title = playlist[index]
    stop_playback()
    print(f"▶️ Playing: {title}")
    mpv_proc = subprocess.Popen(["mpv", "--no-terminal", "--quiet", "--input-ipc-server=/tmp/mpvsocket", url])

def stop_playback():
    global mpv_proc
    if mpv_proc and mpv_proc.poll() is None:
        mpv_proc.terminate()
        mpv_proc.wait()
        mpv_proc = None

def next_song():
    global index
    with lock:
        if repeat_mode == 'one':
            play_current()
            return
        index += 1
        if index >= len(playlist):
            if repeat_mode == 'playlist':
                index = 0
            else:
                print("⏹️ Reached end of playlist.")
                stop_playback()
                return
        play_current()

def prev_song():
    global index
    with lock:
        index = max(0, index - 1)
        play_current()

def shuffle_playlist():
    global index
    random.shuffle(playlist)
    index = 0
    print("🔀 Playlist diacak.")

def handle_commands():
    global repeat_mode
    while True:
        cmd = input("🎧> ").strip()
        if cmd == "p":
            play_current()
        elif cmd == "pau":
            os.system("echo '{\"command\": [\"set_property\", \"pause\", true]}' | socat - /tmp/mpvsocket")
        elif cmd == "n":
            next_song()
        elif cmd == "pre":
            prev_song()
        elif cmd == "s":
            shuffle_playlist()
        elif cmd == "r":
            repeat_mode = 'playlist'
            print("🔁 Repeat playlist diaktifkan.")
        elif cmd == "r1":
            repeat_mode = 'one'
            print("🔂 Repeat satu lagu diaktifkan.")
        elif cmd.startswith("search "):
            query = cmd[7:]
            yt_url, title = get_audio_url(query)
            with lock:
                playlist.append((yt_url, title))
                print(f"🔍 Ditambahkan: {title}")
        elif cmd.startswith("http"):
            yt_url, title = get_audio_url(cmd)
            with lock:
                playlist.append((yt_url, title))
                print(f"➕ Ditambahkan: {title}")
        else:
            print("❓ Perintah tidak dikenali.")

def auto_next_checker():
    global mpv_proc
    while True:
        time.sleep(1)
        if mpv_proc and mpv_proc.poll() is not None:
            next_song()

if __name__ == "__main__":
    print("📻 YT Player ready. Ketik 'p' buat mulai, 'search <judul>', atau tempel URL YouTube.")
    threading.Thread(target=handle_commands, daemon=True).start()
    auto_next_checker()  # run di main thread biar script terus hidup

