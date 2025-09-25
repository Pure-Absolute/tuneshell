from player import MusicPlayer
from youtube import search_youtube
from playlist import list_playlists
import curses

class NcursesUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.player = MusicPlayer()
        self.mode = "home"
        self.selected = 0
        self.search_results = []
        self.multi_select = set()
        self.queue_selected = 0

    def draw(self):
        self.stdscr.clear()
        if self.mode == "home":
            self.draw_home()
        elif self.mode == "search":
            self.draw_search()
        elif self.mode == "queue":
            self.draw_queue()
        elif self.mode == "control":
            self.draw_controls()
        elif self.mode == "playlist":
            self.draw_playlist()
        elif self.mode == "info":
            self.draw_info()
        self.stdscr.refresh()

    def draw_home(self):
        self.stdscr.addstr(0, 0, "Python Music Player (yt-dlp) [Home]")
        self.stdscr.addstr(2, 0, "A: Add first YouTube search result to queue")
        self.stdscr.addstr(3, 0, "/: Search YouTube and add selection to queue")
        self.stdscr.addstr(4, 0, "S: Save queue as playlist")
        self.stdscr.addstr(5, 0, "O: Load playlist")
        self.stdscr.addstr(6, 0, "F: Smart Fill")
        self.stdscr.addstr(7, 0, "?: Show keyboard controls")
        self.stdscr.addstr(8, 0, "L: Show queue")
        self.stdscr.addstr(9, 0, "Y: Toggle auto save")
        self.stdscr.addstr(10,0, "Q: Quit")
        self.stdscr.addstr(11,0, "ESC: Home")
        self.stdscr.addstr(13,0, f"Playing: {self.player.get_current_song()['title'] if self.player.get_current_song() else 'None'}")
        self.stdscr.addstr(14,0, f"Auto Save: {'ON' if self.player.auto_save else 'OFF'}")

    def draw_search(self):
        self.stdscr.addstr(0, 0, "Search YouTube. Enter query:")
        for i, result in enumerate(self.search_results):
            prefix = "> " if i == self.selected else "  "
            selected_tag = "[x]" if i in self.multi_select else "[ ]"
            self.stdscr.addstr(2 + i, 0, f"{prefix}{selected_tag} {result['title']}")
        self.stdscr.addstr(13, 0, "Enter: Add selected | Space: Multi-select | ESC: Cancel")

    def draw_queue(self):
        self.stdscr.addstr(0, 0, "Queue:")
        for i, item in enumerate(self.player.queue):
            prefix = ">" if i == self.queue_selected else " "
            self.stdscr.addstr(2 + i, 0, f"{prefix} {item['title']}")
        self.stdscr.addstr(13, 0, "Enter: Play | Del/Backspace: Remove | Z: Up | X: Down | I: Info | ESC: Home")

    def draw_controls(self):
        controls = [
            "A: Add first search result to queue",
            "/: Search and add to queue",
            "S: Save queue as playlist",
            "O: Load playlist",
            "F: Smart Fill",
            "?: Controls",
            "L: Show queue",
            "Y: Toggle auto save",
            "ESC: Home",
            "Q: Quit",
            "Space: Play/Pause",
            "Left: Previous song",
            "Right: Next song",
            "R: Repeat one",
            "T: Repeat queue",
            "H: Shuffle queue",
        ]
        self.stdscr.addstr(0, 0, "Keyboard Controls:")
        for i, c in enumerate(controls):
            self.stdscr.addstr(2 + i, 0, c)
        self.stdscr.addstr(20, 0, "ESC: Home")

    def draw_playlist(self):
        names = list_playlists()
        for i, name in enumerate(names):
            prefix = ">" if i == self.selected else " "
            self.stdscr.addstr(2 + i, 0, f"{prefix} {name}")
        self.stdscr.addstr(0, 0, "Playlists: Enter to load | ESC: Home")

    def draw_info(self):
        song = self.player.get_current_song()
        if song:
            self.stdscr.addstr(0, 0, f"Title: {song['title']}")
            self.stdscr.addstr(1, 0, f"ID: {song['id']}")
            self.stdscr.addstr(2, 0, f"URL: {song['url']}")
        self.stdscr.addstr(4, 0, "ESC: Back")

    def run(self):
        curses.curs_set(0)
        self.draw()
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if self.mode == "home":
                if ch == ord('A'):
                    self.stdscr.addstr(15, 0, "Query: ")
                    curses.echo()
                    query = self.stdscr.getstr(15, 8, 30).decode()
                    curses.noecho()
                    results = search_youtube(query, 1)
                    if results:
                        self.player.add_to_queue(results[0])
                elif ch == ord('/'):
                    self.stdscr.addstr(15, 0, "Query: ")
                    curses.echo()
                    query = self.stdscr.getstr(15, 8, 30).decode()
                    curses.noecho()
                    self.search_results = search_youtube(query, 10)
                    self.multi_select = set()
                    self.selected = 0
                    self.mode = "search"
                elif ch == ord('S'):
                    self.stdscr.addstr(15, 0, "Playlist name: ")
                    curses.echo()
                    name = self.stdscr.getstr(15, 15, 30).decode()
                    curses.noecho()
                    self.player.set_playlist_name(name)
                    self.player.save_current_playlist()
                    self.player.auto_save = True
                elif ch == ord('O'):
                    self.mode = "playlist"
                    self.selected = 0
                elif ch == ord('F'):
                    self.player.smart_fill_enabled = True
                elif ch == ord('?'):
                    self.mode = "control"
                elif ch == ord('L'):
                    self.mode = "queue"
                    self.queue_selected = 0
                elif ch == ord('Y'):
                    self.player.toggle_auto_save()
                elif ch == 27: # ESC
                    self.mode = "home"
                elif ch == ord('Q'):
                    self.player.stop()
                    break
                elif ch == ord(' '):
                    if self.player.is_playing:
                        if self.player.is_paused:
                            self.player.resume()
                        else:
                            self.player.pause()
                    else:
                        self.player.play()
                elif ch == curses.KEY_RIGHT:
                    self.player.next()
                elif ch == curses.KEY_LEFT:
                    self.player.prev()
                elif ch == ord('R'):
                    self.player.repeat_one = not self.player.repeat_one
                elif ch == ord('T'):
                    self.player.repeat_queue = not self.player.repeat_queue
                elif ch == ord('H'):
                    self.player.shuffle = not self.player.shuffle
            elif self.mode == "search":
                if ch == curses.KEY_UP:
                    self.selected = max(0, self.selected - 1)
                elif ch == curses.KEY_DOWN:
                    self.selected = min(len(self.search_results) - 1, self.selected + 1)
                elif ch == ord(' '):
                    if self.selected in self.multi_select:
                        self.multi_select.remove(self.selected)
                    else:
                        self.multi_select.add(self.selected)
                elif ch == 10: # Enter
                    to_add = [self.search_results[i] for i in (self.multi_select if self.multi_select else [self.selected])]
                    self.player.add_multiple_to_queue(to_add)
                    self.mode = "home"
                elif ch == 27: # ESC
                    self.mode = "home"
            elif self.mode == "queue":
                if ch == curses.KEY_UP:
                    self.queue_selected = max(0, self.queue_selected - 1)
                elif ch == curses.KEY_DOWN:
                    self.queue_selected = min(len(self.player.queue) - 1, self.queue_selected + 1)
                elif ch == ord('Z'):
                    self.player.move_up(self.queue_selected)
                    self.queue_selected = max(0, self.queue_selected - 1)
                elif ch == ord('X'):
                    self.player.move_down(self.queue_selected)
                    self.queue_selected = min(len(self.player.queue) - 1, self.queue_selected + 1)
                elif ch == ord('I'):
                    self.mode = "info"
                elif ch == curses.KEY_DC or ch == 127:
                    self.player.remove_from_queue(self.queue_selected)
                    self.queue_selected = max(0, self.queue_selected - 1)
                elif ch == 10: # Enter
                    self.player.play(self.queue_selected)
                elif ch == 27: # ESC
                    self.mode = "home"
            elif self.mode == "control":
                if ch == 27:
                    self.mode = "home"
            elif self.mode == "playlist":
                names = list_playlists()
                if ch == curses.KEY_UP:
                    self.selected = max(0, self.selected - 1)
                elif ch == curses.KEY_DOWN:
                    self.selected = min(len(names) - 1, self.selected + 1)
                elif ch == 10: # Enter
                    self.player.load_playlist(names[self.selected])
                    self.mode = "home"
                elif ch == 27:
                    self.mode = "home"
            elif self.mode == "info":
                if ch == 27:
                    self.mode = "queue"