"""
Command-line entry point.  Installed as the ``annotate`` console script.

Usage
-----
::

    annotate                              # GUI dialog — pick 1 or 2 videos
    annotate top.mp4                      # single-view
    annotate top.mp4 front.mp4            # dual-view: FRONT = master clock,
                                          # top stretched by frame-count rate
"""

from __future__ import annotations

import argparse

from .storage import select_videos
from .player import Player


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="annotate",
        description="Frame-accurate behavioral annotation tool.",
    )
    parser.add_argument(
        "videos",
        nargs="*",
        metavar="VIDEO",
        help="0, 1, or 2 video paths.  "
             "0 → GUI dialog.  1 → single-view.  2 → dual-view (top front); "
             "front is the master, CSV is named after the front video.",
    )
    args = parser.parse_args()

    # ── Resolve video paths ──────────────────────────────────────────────────
    if len(args.videos) == 2:
        path1, path2 = args.videos
    elif len(args.videos) == 1:
        path1, path2 = args.videos[0], None
    else:
        path1, path2 = select_videos()

    if not path1:
        print("No video selected. Exiting.")
        return

    Player(path1, path2).run()
