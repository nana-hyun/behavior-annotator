"""
Mouse state and OpenCV mouse-callback for timeline scrubbing.
"""

from __future__ import annotations

import cv2
from .config import BAR_H, MARGIN


def bar_top(disp_h: int) -> int:
    """Y-coordinate of the top edge of the timeline bar."""
    return disp_h - 62 - BAR_H - 6


def x_to_frame(x: int, disp_w: int, total_frames: int) -> int:
    """Convert a pixel x-position on the timeline to a frame index."""
    ratio = (x - MARGIN) / max(1, disp_w - 2 * MARGIN)
    return int(max(0.0, min(1.0, ratio)) * (total_frames - 1))


def frame_to_x(frame: int, disp_w: int, total_frames: int) -> int:
    """Convert a frame index to a pixel x-position on the timeline."""
    return MARGIN + int(frame / total_frames * (disp_w - 2 * MARGIN))


def make_mouse_state() -> dict:
    return {
        "dragging":   False,
        "in_bar":     False,
        "hover_x":    -1,
        "hover_y":    -1,
        "seek_frame": None,   # set on click/drag; consumed by the player loop
    }


def make_mouse_callback(state: dict, disp_w: int, disp_h: int, total_frames: int):
    """
    Return an OpenCV mouse callback that updates *state* in-place.

    The callback handles:
    - Left-click on the timeline bar  → seek
    - Drag while holding left button  → live scrub
    - Mouse move                      → hover highlight
    """
    HIT_MARGIN = 8  # px above/below bar that still counts as a hit

    def callback(event, x, y, flags, param):
        top  = bar_top(disp_h)
        y_lo = top - HIT_MARGIN
        y_hi = top + BAR_H + HIT_MARGIN

        if event == cv2.EVENT_LBUTTONDOWN:
            if y_lo <= y <= y_hi:
                state["dragging"]   = True
                state["seek_frame"] = x_to_frame(x, disp_w, total_frames)

        elif event == cv2.EVENT_MOUSEMOVE:
            state["hover_x"] = x
            state["hover_y"] = y
            state["in_bar"]  = y_lo <= y <= y_hi
            if state["dragging"]:
                state["seek_frame"] = x_to_frame(x, disp_w, total_frames)

        elif event == cv2.EVENT_LBUTTONUP:
            if state["dragging"]:
                state["seek_frame"] = x_to_frame(x, disp_w, total_frames)
            state["dragging"] = False

    return callback
