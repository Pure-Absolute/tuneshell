import curses
from ui import NcursesUI

def main(stdscr):
    ui = NcursesUI(stdscr)
    ui.run()

if __name__ == "__main__":
    curses.wrapper(main)