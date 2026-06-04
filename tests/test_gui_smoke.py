"""
Headless-ish smoke test: build the main window, pump the event loop briefly,
then destroy. Catches import errors, widget-construction bugs, and callback
wiring issues without a human clicking anything.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tkinter as tk

from gui.main_window import MainWindow


def main():
    root = tk.Tk()
    win = MainWindow(root)

    # exercise a few thread-safe UI paths directly
    win._update_counts({"total": 100, "sent": 10, "failed": 2, "pending": 88, "opened": 4})
    win._append_log("success", "test success line")
    win._append_log("error", "test error line")
    win._set_state_label("running")
    win._set_countdown(42)
    win._set_state_label("done")

    # pump the event loop ~0.5s then close
    def shutdown():
        if win.db:
            win.db.close()
        root.destroy()

    root.after(500, shutdown)
    root.mainloop()
    print("OK - GUI smoke test passed (window built, events pumped, closed cleanly)")


if __name__ == "__main__":
    main()
