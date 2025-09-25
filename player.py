from playlist import save_playlist, load_playlist
from youtube import get_audio_url, search_youtube
from collections import deque
import subprocess
import threading

class MusicPlayer:
    def __init__(self):
        self.queue = deque()
        self.history = []
        self.current_index = None
        self.is_playing = False
        self.is_paused = False
        self.process = None
        self.repeat_one = False
        self.repeat_queue = False
        self.shuffle = False
        self.auto_save = False
        self.playlist_name = None
        self.progress = 0
        self.duration = 0
        self.smart_fill_enabled = False

    def add_to_queue(self, item):
        self.queue.append(item)
        if self.auto_save and self.playlist_name:
            self.save_current_playlist()

    def add_multiple_to_queue(self, items):
        self.queue.extend(items)
        if self.auto_save and self.playlist_name:
            self.save_current_playlist()

    def save_current_playlist(self):
        save_playlist(self.playlist_name, list(self.queue))

    def remove_from_queue(self, index):
        try:
            removed = self.queue[index]
            del self.queue[index]
            if self.auto_save and self.playlist_name:
                self.save_current_playlist()
            return removed
        except IndexError:
            return None

    def move_up(self, index):
        if index > 0:
            self.queue[index - 1], self.queue[index] = self.queue[index], self.queue[index - 1]
            if self.auto_save and self.playlist_name:
                self.save_current_playlist()

    def move_down(self, index):
        if index < len(self.queue) - 1:
            self.queue[index + 1], self.queue[index] = self.queue[index], self.queue[index + 1]
            if self.auto_save and self.playlist_name:
                self.save_current_playlist()

    def play(self, index=None):
        if len(self.queue) == 0:
            return
        if index is not None:
            self.current_index = index
        elif self.current_index is None:
            self.current_index = 0
        self.stop()
        item = self.queue[self.current_index]
        audio_url = get_audio_url(item['url'])
        if not audio_url:
            return
        self.is_playing = True
        self.is_paused = False
        self.progress = 0
        self.process = subprocess.Popen(['mpv', '--no-video', audio_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self._monitor_playback, daemon=True).start()

    def _monitor_playback(self):
        if self.process:
            self.process.wait()
            self.is_playing = False
            self.progress = 0
            if self.repeat_one:
                self.play(self.current_index)
            elif self.repeat_queue:
                self.next()
            elif self.shuffle:
                import random
                self.current_index = random.randint(0, len(self.queue) - 1)
                self.play(self.current_index)
            else:
                self.next()

    def pause(self):
        if self.process and self.is_playing:
            self.process.send_signal(subprocess.signal.SIGSTOP)
            self.is_paused = True

    def resume(self):
        if self.process and self.is_paused:
            self.process.send_signal(subprocess.signal.SIGCONT)
            self.is_paused = False

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process = None
        self.is_playing = False
        self.is_paused = False

    def next(self):
        if not self.queue:
            return
        if self.current_index is None:
            self.current_index = 0
        else:
            self.current_index += 1
            if self.current_index >= len(self.queue):
                if self.smart_fill_enabled:
                    self.smart_fill()
                else:
                    self.current_index = 0
        self.play(self.current_index)

    def prev(self):
        if not self.queue:
            return
        if self.current_index is None or self.current_index == 0:
            self.current_index = len(self.queue) - 1
        else:
            self.current_index -= 1
        self.play(self.current_index)

    def smart_fill(self):
        if self.current_index and self.current_index < len(self.queue):
            last_id = self.queue[self.current_index - 1]['id']
            recs = search_youtube(f"related:{last_id}", max_results=1)
            if recs:
                rec = recs[0]
                rec['title'] = f"✨ (fill) {rec['title']}"
                self.queue.append(rec)
                self.current_index = len(self.queue) - 1
                self.play(self.current_index)

    def toggle_auto_save(self):
        self.auto_save = not self.auto_save
        if self.auto_save and self.playlist_name:
            self.save_current_playlist()

    def set_playlist_name(self, name):
        self.playlist_name = name

    def load_playlist(self, name):
        self.queue = deque(load_playlist(name))
        self.playlist_name = name
        self.auto_save = True

    def get_current_song(self):
        if self.current_index is not None and self.current_index < len(self.queue):
            return self.queue[self.current_index]
        return None