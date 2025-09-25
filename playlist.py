import os
import json

PLAYLISTS_DIR = "playlists"

def ensure_playlists_dir():
    if not os.path.exists(PLAYLISTS_DIR):
        os.makedirs(PLAYLISTS_DIR)

def save_playlist(name, queue):
    ensure_playlists_dir()
    path = os.path.join(PLAYLISTS_DIR, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

def load_playlist(name):
    path = os.path.join(PLAYLISTS_DIR, name + ".json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def list_playlists():
    ensure_playlists_dir()
    return [f[:-5] for f in os.listdir(PLAYLISTS_DIR) if f.endswith(".json")]