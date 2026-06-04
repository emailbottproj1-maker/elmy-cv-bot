"""
Elmy CV Bot — desktop entry point.

Run:  python main.py
Build .exe:  see build.bat
"""
from __future__ import annotations

import os
import sys
import tkinter as tk

# Ensure the project root is importable whether run as script or frozen exe.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

os.makedirs("data", exist_ok=True)

from gui.main_window import MainWindow  # noqa: E402


def main() -> None:
    root = tk.Tk()
    try:
        if os.path.exists("assets/icon.ico"):
            root.iconbitmap("assets/icon.ico")
    except Exception:
        pass
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
