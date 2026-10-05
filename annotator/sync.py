"""
Frame-synchronization helpers.

Two modes
---------
Ratio mode  (no FFmpeg, used inside the Player)
    Compute the front-video frame index that corresponds to a given top-video
    frame index:  front_frame = round(top_frame * ratio)

FFmpeg mode  (batch pre-processing, used by the ``sync-videos`` CLI)
    Re-encode the front video with a stretched PTS so its total duration
    matches the top video.  Slower but produces a standalone .mp4 file that
    any player can open in sync.
"""

from __future__ import annotations

import os
import subprocess
import cv2


# ── Ratio mode (live, no FFmpeg) ──────────────────────────────────────────────

def compute_ratio(top_total_frames: int, front_total_frames: int) -> float:
    """
    Return the scalar that converts a top-video frame index into the
    corresponding front-video frame index.

    Usage inside Player::

        front_frame = round(top_frame * self._front_ratio)

    When both videos have the same frame count the ratio is exactly 1.0 and
    seeking is unchanged — no correction is applied.
    """
    return front_total_frames / max(1, top_total_frames)


# ── FFmpeg mode (batch pre-processing) ───────────────────────────────────────

def synced_path(front_path: str) -> str:
    """
    Return the expected output path for a pre-synced copy of *front_path*.

    Example
    -------
    ``Aggw3_ctrl01_front_2026-10-05T15_12_07.avi``
    → ``Aggw3_ctrl01_front_2026-10-05T15_12_07_sync.avi``
    """
    stem, ext = os.path.splitext(front_path)
    return f"{stem}_sync{ext}"


def _video_info(path: str) -> tuple[int, float]:
    """Return (frame_count, fps) for *path*."""
    cap = cv2.VideoCapture(path)
    n   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return n, fps


def duration_diff(top_path: str, front_path: str) -> float:
    """Return |top_duration − front_duration| in seconds."""
    top_n,   top_fps   = _video_info(top_path)
    front_n, front_fps = _video_info(front_path)
    return abs(top_n / top_fps - front_n / front_fps)


def sync_front_to_top(top_path: str, front_path: str, output_path: str) -> bool:
    """
    Re-encode *front_path* with FFmpeg so its playback duration matches
    *top_path*.

    The ``setpts`` filter scales every frame's presentation timestamp by
    ``top_duration / front_duration``.  No frames are added or dropped; the
    video simply plays faster or slower.

    Parameters
    ----------
    top_path    : reference video (top view)
    front_path  : video to stretch (front view)
    output_path : destination file (created or overwritten)

    Returns
    -------
    True on success, False if FFmpeg is missing or returns a non-zero exit code.
    """
    top_n,   top_fps   = _video_info(top_path)
    front_n, front_fps = _video_info(front_path)

    if top_fps == 0 or front_fps == 0:
        print("  [sync] Error: could not read FPS — is FFmpeg installed?")
        return False

    top_dur   = top_n   / top_fps
    front_dur = front_n / front_fps
    pts_mult  = top_dur / front_dur

    print(f"  [sync] top  : {top_n} frames @ {top_fps:.2f} fps = {top_dur:.2f}s")
    print(f"  [sync] front: {front_n} frames @ {front_fps:.2f} fps = {front_dur:.2f}s")
    print(f"  [sync] output → {output_path}")

    if front_dur > top_dur:
        offset_secs = front_dur - top_dur
        # Front is longer — it started recording earlier.
        # Skip the preamble (first offset_secs) and keep the last top_dur seconds.
        # Stream-copy (no re-encode): very fast, lossless quality.
        print(f"  [sync] Mode: TRIM  (skip first {offset_secs:.3f}s preamble → keep last {top_dur:.3f}s)")
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{offset_secs:.6f}",
            "-i", front_path,
            "-t", f"{top_dur:.6f}",
            "-c", "copy",
            output_path,
        ]
    else:
        # Front is shorter — stretch PTS so it fills the top duration.
        # Requires re-encode; slower but rarely needed.
        print(f"  [sync] Mode: STRETCH  PTS × {pts_mult:.6f}")
        cmd = [
            "ffmpeg", "-y",
            "-i", front_path,
            "-filter:v", f"setpts=({pts_mult:.8f})*PTS",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            output_path,
        ]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("  [sync] FFmpeg not found. Install it: https://ffmpeg.org/download.html")
        return False

    if result.returncode != 0:
        tail = result.stderr.decode(errors="replace")[-600:]
        print(f"  [sync] FFmpeg error:\n{tail}")
    return result.returncode == 0
