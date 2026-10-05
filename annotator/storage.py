"""
CSV persistence and video-file selection dialog.
"""

from __future__ import annotations

import os
import re
import pandas as pd


CSV_COLUMNS = [
    'behavior', 'start_frame', 'start_sec',
    'end_frame', 'end_sec', 'duration_sec',
]
# Extra reference columns written only in dual-view mode (top-video frame indices).
EXTRA_COLUMNS = ['start_top_frame', 'end_top_frame']

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
        title="Select a video (top or front — order doesn't matter)",
        filetypes=_VIDEO_FILETYPES,
    )
    if not path1:
        root.destroy()
        return None, None

    add_second = messagebox.askyesno(
        "Second camera angle",
        "Add the other camera angle (top or front, any order)?\n\nClick No to use a single video.",
    )
    path2 = None
    if add_second:
        path2 = filedialog.askopenfilename(
            title="Select the other camera video",
            filetypes=_VIDEO_FILETYPES,
        )

    root.destroy()
    return path1, path2


def _view_of(path: str) -> str | None:
    """'top' / 'front' if the file name says so, else None."""
    name = os.path.splitext(os.path.basename(path))[0].lower()
    tokens = set(re.split(r"[^a-z0-9]+", name))
    has_top, has_front = "top" in tokens, "front" in tokens
    if has_top == has_front:                     # neither or both as words
        has_top, has_front = "top" in name, "front" in name
    if has_top and not has_front:
        return "top"
    if has_front and not has_top:
        return "front"
    return None


def order_top_front(a: str, b: str) -> tuple[str, str]:
    """
    Return (top_path, front_path) whatever order the two files were picked in,
    using "top" / "front" in the file names.  If the names don't tell, the
    given order is kept (a = top, b = front) and a warning is printed.
    """
    va, vb = _view_of(a), _view_of(b)
    if va == "front" or vb == "top":
        if va != vb:
            print("  [player] Picked in front→top order — swapped automatically.")
            return b, a
    if not (va == "top" or vb == "front"):
        print("  [player] Warning: can't tell top/front from the file names — "
              f"using {os.path.basename(a)} as TOP and {os.path.basename(b)} as FRONT.")
    return a, b


def csv_path_for(video_path: str) -> str:
    """
    Return the annotation CSV path for *video_path*.

    The CSV is named after the **master video** (the front view in dual mode,
    the only video in single mode), the one whose frames are counted.

    Example
    -------
    ``Aggw3_ctrl01_front_2026-10-05T15_12_07.avi``
    → ``Aggw3_ctrl01_front_2026-10-05T15_12_07_annotations.csv``
    """
    directory = os.path.dirname(video_path)
    stem      = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(directory, stem + "_annotations.csv")


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
        cols = CSV_COLUMNS + [c for c in EXTRA_COLUMNS
                              if any(c in a for a in annotations)]
        df = pd.DataFrame(annotations, columns=cols)
        df.to_csv(path, index=False)
        print(f"  [storage] Saved {len(df)} rows → {path}")
    else:
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(path, index=False)
        print("  [storage] No annotations to save.")
