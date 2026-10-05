from __future__ import annotations

import sys
from .storage import select_videos
from .player import Player


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

    Player(path1, path2).run()