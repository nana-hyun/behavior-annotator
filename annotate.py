#!/usr/bin/env python3
"""
Entry point for the Behavior Annotator.

Usage
-----
  python annotate.py                          # GUI dialog to pick 1 or 2 videos
  python annotate.py top.mp4                  # single-view mode
  python annotate.py top.mp4 front.mp4        # dual-view mode (side by side)
"""

import sys
from annotator.storage import select_videos
from annotator.player import Player


def main() -> None:
    if len(sys.argv) == 3:
        path1, path2 = sys.argv[1], sys.argv[2]
    elif len(sys.argv) == 2:
        path1, path2 = sys.argv[1], None
    else:
        path1, path2 = select_videos()

    if not path1:
        print("No video selected. Exiting.")
        return

    player = Player(path1, path2)
    player.run()


if __name__ == "__main__":
    main()
