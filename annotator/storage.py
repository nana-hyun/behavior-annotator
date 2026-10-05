"""
CSV persistence and video-file selection dialog.
"""

from __future__ import annotations

import os
import pandas as pd


CSV_COLUMNS = [
    'behavior', 'start_frame', 'start_sec',
    'end_frame', 'end_sec', 'duration_sec',
]

_VIDEO_FILETYPES = [("Video files", "*.mp4 *.avi *.mov *.mkv *.MP4")]


def select_videos() -> tuple[str | None, str | None]:
    """
    Open Tk file dialogs to pick one or two video files.

    Returns
    -------
    (path1, path2)
        path2 is None when the user declines a second file.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()

    path1 = filedialog.askopenfilename(
        title="Select primary video (top view, or only video)",
        filetypes=_VIDEO_FILETYPES,
    )
    if not path1:
        root.destroy()
        return None, None

    add_second = messagebox.askyesno(
        "Second camera angle",
        "Add a second camera angle (e.g. front view)?\n\nClick No to use a single video.",
    )
    path2 = None
    if add_second:
        path2 = filedialog.askopenfilename(
            title="Select second video (front view)",
            filetypes=_VIDEO_FILETYPES,
        )

    root.destroy()
    return path1, path2


def csv_path_for(video_path: str) -> str:
    """Return the annotation CSV path that corresponds to *video_path*."""
    return os.path.splitext(video_path)[0] + "_annotations.csv"


def load_csv(path: str) -> list[dict]:
    """
    Load annotations from *path*.

    Returns an empty list if the file does not exist or is empty.
    Prints a warning on parse error.
    """
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
        if df.empty:
            return []
        return df.to_dict("records")
    except Exception as exc:
        print(f"  [storage] Could not read {path}: {exc} — starting fresh")
        return []


def save_csv(path: str, annotations: list[dict]) -> None:
    """Write *annotations* to *path*, or write an empty CSV when the list is empty."""
    if annotations:
        df = pd.DataFrame(annotations, columns=CSV_COLUMNS)
        df.to_csv(path, index=False)
        print(f"  [storage] Saved {len(df)} rows → {path}")
    else:
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(path, index=False)
        print("  [storage] No annotations to save.")
