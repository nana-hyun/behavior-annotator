"""
Batch front-to-top video synchronization.

Installed as the ``sync-videos`` console script.

Usage
-----
::

    sync-videos /path/to/folder
    sync-videos /path/to/folder --ext mp4

The command scans *folder* for every ``*_top_*`` video, finds its matching
``*_front_*`` counterpart, and re-encodes it via FFmpeg so its duration
exactly matches the top view.  Already-synced files (``*_sync.*``) are
skipped.  The annotator's built-in ratio-based sync works without this step,
but pre-processing guarantees that every tool (VLC, etc.) plays the pair in
lockstep.
"""

from __future__ import annotations

import os
import glob
import argparse

from .sync import sync_front_to_top, synced_path, duration_diff

_SKIP_THRESHOLD = 0.1   # seconds — durations closer than this are treated as identical


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Find every *_top_* video in FOLDER and sync its *_front_* pair "
            "by stretching the front video's PTS to match the top video's duration."
        )
    )
    parser.add_argument(
        "folder_path",
        help="Folder containing top/front video pairs.",
    )
    parser.add_argument(
        "--ext",
        default="avi",
        metavar="EXT",
        help="Video file extension to search for (default: avi).  "
             "Use 'mp4' for MP4 files, etc.",
    )
    args = parser.parse_args()

    folder = args.folder_path
    if not os.path.isdir(folder):
        print(f"Error: folder not found → {folder}")
        return

    ext      = args.ext.lstrip(".")
    pattern  = os.path.join(folder, f"*_top_*.{ext}")
    top_files = sorted(glob.glob(pattern))

    if not top_files:
        print(f"No '*_top_*.{ext}' files found in:\n  {folder}")
        return

    print(f"Found {len(top_files)} top video(s) — starting sync…")
    print("─" * 60)

    ok_count = fail_count = skip_count = 0

    for top_path in top_files:
        front_path = top_path.replace("_top_", "_front_")

        if not os.path.exists(front_path):
            print(f"[SKIP] No matching front video: {os.path.basename(top_path)}")
            skip_count += 1
            continue

        out_path = synced_path(front_path)

        if os.path.exists(out_path):
            print(f"[SKIP] Already synced: {os.path.basename(out_path)}")
            skip_count += 1
            continue

        diff = duration_diff(top_path, front_path)
        if diff <= _SKIP_THRESHOLD:
            print(f"[SKIP] Durations match (Δ={diff:.3f}s ≤ {_SKIP_THRESHOLD}s): "
                  f"{os.path.basename(front_path)}")
            skip_count += 1
            continue

        print(f"\n[SYNC] {os.path.basename(front_path)}  (Δ={diff:.3f}s)")
        success = sync_front_to_top(top_path, front_path, out_path)

        if success:
            print(f"  → Done: {os.path.basename(out_path)}")
            ok_count += 1
        else:
            print("  → Failed.")
            fail_count += 1

    print("\n" + "─" * 60)
    print(f"Finished — {ok_count} synced, {skip_count} skipped, {fail_count} failed.")