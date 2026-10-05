"""
All rendering helpers: font loading, text, timeline bar, and the full overlay.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import BEHAVIORS, COLORS, BAR_H, MARGIN, TOP_PAD
from .mouse import bar_top, frame_to_x, x_to_frame


# ── Font ──────────────────────────────────────────────────────────────────────

_FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = _load_font(size)
    return _FONT_CACHE[size]


# ── Text helper ───────────────────────────────────────────────────────────────

_TEXT_CACHE: dict[tuple, tuple] = {}


def _text_masks(text: str, size: int, bold: bool):
    """Rendered glyph masks for *text* (cached): (fill, outline, dx, dy)."""
    key = (text, size, bold)
    hit = _TEXT_CACHE.get(key)
    if hit is not None:
        return hit
    font = get_font(size)
    try:
        l, t, r, b = font.getbbox(text)
    except AttributeError:                      # very old Pillow
        l, t, (r, b) = 0, 0, font.getsize(text)
    pad = 2
    w, h = max(1, r - l + 2 * pad), max(1, b - t + 2 * pad)
    ox, oy = pad - l, pad - t
    fill = Image.new("L", (w, h), 0)
    ImageDraw.Draw(fill).text((ox, oy), text, font=font, fill=255)
    outline = None
    if bold:
        outline = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(outline)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            d.text((ox + dx, oy + dy), text, font=font, fill=255)
        outline = np.asarray(outline, np.float32)[..., None] / 255.0
    res = (np.asarray(fill, np.float32)[..., None] / 255.0, outline, l - pad, t - pad)
    if len(_TEXT_CACHE) > 1024:
        _TEXT_CACHE.clear()
    _TEXT_CACHE[key] = res
    return res


def put_text(
    img_bgr: np.ndarray,
    text: str,
    xy: tuple[int, int],
    size: int = 22,
    color: tuple[int, int, int] = (255, 255, 255),
    bold: bool = False,
) -> None:
    """
    Render *text* (colour given as RGB) onto a BGR image, in place.

    Glyphs are rendered once by PIL and cached as masks; each frame only blends
    the small rectangle under the text.  (Converting the whole frame to PIL for
    every label used to make playback several times slower than real time.)
    """
    fill, outline, dx, dy = _text_masks(text, size, bold)
    H, W = img_bgr.shape[:2]
    x0, y0 = xy[0] + dx, xy[1] + dy
    h, w = fill.shape[:2]
    # clip to image
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(W, x0 + w), min(H, y0 + h)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    sl = (slice(cy0 - y0, cy1 - y0), slice(cx0 - x0, cx1 - x0))
    roi = img_bgr[cy0:cy1, cx0:cx1].astype(np.float32)
    if outline is not None:
        roi *= 1.0 - outline[sl]
    f = fill[sl]
    bgr = np.array(color[::-1], np.float32)
    roi = roi * (1.0 - f) + bgr * f
    img_bgr[cy0:cy1, cx0:cx1] = roi.astype(np.uint8)


def shade(img: np.ndarray, x0: int, y0: int, x1: int, y1: int,
          color: tuple[int, int, int], alpha: float) -> None:
    """Blend a solid *color* (BGR) into a rectangle — touches only that region."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    roi = img[y0:y1, x0:x1]
    solid = np.empty_like(roi)
    solid[:] = color
    img[y0:y1, x0:x1] = cv2.addWeighted(solid, alpha, roi, 1 - alpha, 0)


# ── Frame composition ─────────────────────────────────────────────────────────

def compose_display(
    frame1: np.ndarray,
    frame2: np.ndarray | None,
    disp_w: int,
    disp_h: int,
    dual: bool,
    labels: tuple[str, str] = ("TOP", "FRONT"),
) -> np.ndarray:
    """
    Compose the final display canvas.

    The video is placed in a dedicated middle strip (starting at TOP_PAD),
    leaving a black band at the top (top info bar) and bottom (timeline +
    shortcut bar) so HUD elements never overlap the video content.

    In dual mode the two frames are placed side by side with camera labels
    ("TOP" / "FRONT") and a thin divider line.
    """
    vid_h = frame1.shape[0]

    # Black canvas — HUD areas start transparent/black, overlays are drawn later
    canvas = np.zeros((disp_h, disp_w, 3), dtype=np.uint8)

    if not dual or frame2 is None:
        canvas[TOP_PAD:TOP_PAD + vid_h, :] = frame1
    else:
        video_strip = np.hstack([frame1, frame2])
        canvas[TOP_PAD:TOP_PAD + vid_h, :] = video_strip

        half = disp_w // 2
        # Vertical divider — only through the video area
        cv2.line(canvas, (half, TOP_PAD), (half, TOP_PAD + vid_h), (60, 60, 60), 1)

        # Camera labels ("TOP" / "FRONT") drawn inside the video area
        label_y = TOP_PAD + 4
        for x_off, label in [(8, labels[0]), (half + 8, labels[1])]:
            tw = int(get_font(20).getlength(label)) + 12
            shade(canvas, x_off - 4, label_y, x_off + tw, label_y + 29,
                  (10, 10, 10), 0.55)
            put_text(canvas, label, (x_off + 4, label_y + 4),
                     size=20, color=(200, 200, 200), bold=True)

    return canvas


# ── Timeline bar ──────────────────────────────────────────────────────────────

def draw_timeline(
    display: np.ndarray,
    current_frame: int,
    total_frames: int,
    annotations: list[dict],
    active: dict[str, int],
    mouse_state: dict,
) -> None:
    """Draw the color-coded, interactive timeline bar at the bottom of *display*."""
    h, w = display.shape[:2]
    top  = bar_top(h)

    # Dark background strip
    shade(display, 0, top - 2, w, top + BAR_H + 3, (10, 10, 10), 0.72)

    # Bar background (highlights on hover / drag)
    bar_bg = (65, 65, 65) if (mouse_state["in_bar"] or mouse_state["dragging"]) else (45, 45, 45)
    cv2.rectangle(display, (MARGIN, top), (w - MARGIN, top + BAR_H), bar_bg, -1)

    # Completed annotations
    for ann in annotations:
        col    = COLORS.get(ann["behavior"], (180, 180, 180))
        col_cv = (col[2], col[1], col[0])
        x1 = frame_to_x(ann["start_frame"], w, total_frames)
        x2 = max(frame_to_x(ann["end_frame"], w, total_frames), x1 + 3)
        cv2.rectangle(display, (x1, top + 1), (x2, top + BAR_H - 1), col_cv, -1)

    # Active (in-progress) annotations — blinking
    for beh, start_f in active.items():
        col    = COLORS.get(beh, (180, 180, 180))
        col_cv = (col[2], col[1], col[0])
        x1 = frame_to_x(start_f,        w, total_frames)
        x2 = max(frame_to_x(current_frame, w, total_frames), x1 + 3)
        blink = 0.5 + 0.5 * abs(((current_frame // 8) % 2) * 2 - 1)
        shade(display, x1, top + 1, x2 + 1, top + BAR_H, col_cv, blink)

    # Hover ghost playhead + time tooltip
    if mouse_state["in_bar"] and not mouse_state["dragging"]:
        hx = mouse_state["hover_x"]
        if MARGIN <= hx <= w - MARGIN:
            cv2.line(display, (hx, top - 3), (hx, top + BAR_H + 3), (180, 180, 180), 1)
            ghost_f = x_to_frame(hx, w, total_frames)
            put_text(display, f"{ghost_f / max(1, total_frames) * total_frames / 30:.2f}s",
                     (max(MARGIN, hx - 26), top - 22), size=14, color=(200, 200, 200))

    # Main playhead
    px = frame_to_x(current_frame, w, total_frames)
    cv2.line(display, (px, top - 4), (px, top + BAR_H + 4), (255, 255, 255), 2)

    # Drag playhead (bright blue)
    if mouse_state["dragging"] and mouse_state["seek_frame"] is not None:
        sx = frame_to_x(mouse_state["seek_frame"], w, total_frames)
        cv2.line(display, (sx, top - 6), (sx, top + BAR_H + 6), (80, 200, 255), 3)

    # Behavior color legend (small squares above bar)
    legend_x = MARGIN + 4
    for beh in BEHAVIORS.values():
        col = COLORS.get(beh, (180, 180, 180))
        put_text(display, f"■{beh[0]}", (legend_x, top - 18), size=13, color=col)
        legend_x += 38


# ── Full overlay ──────────────────────────────────────────────────────────────

def draw_overlay(
    display: np.ndarray,
    current_frame: int,
    total_frames: int,
    fps: float,
    playing: bool,
    active: dict[str, int],
    annotations: list[dict],
    undo_flash: list,
    mouse_state: dict,
) -> None:
    """Draw all HUD elements (top bar, status, timeline, bottom bar) onto *display* in-place."""
    h, w = display.shape[:2]

    def _sec(frame: int) -> float:
        return round(frame / fps, 3)

    # ── Top bar ───────────────────────────────────────────────────────────────
    shade(display, 0, 0, w, 57, (15, 15, 15), 0.7)

    put_text(display,
             f"Frame {current_frame} / {total_frames}     Time  {_sec(current_frame):.2f} s",
             (14, 14), size=26, color=(240, 240, 240), bold=True)

    # Active-behavior pills with elapsed time
    pill_x = 520
    for beh, sf in active.items():
        col   = COLORS.get(beh, (255, 255, 255))
        label = f"● {beh}  {_sec(current_frame - sf):.1f}s"
        put_text(display, label, (pill_x, 14), size=21, color=col, bold=True)
        pill_x += len(label) * 11 + 10

    status = "PLAYING" if playing else "PAUSED"
    color  = (80, 220, 80) if playing else (100, 180, 255)
    put_text(display, status, (w - 160, 14), size=26, color=color, bold=True)

    # ── Undo flash ────────────────────────────────────────────────────────────
    if undo_flash[0] > 0:
        put_text(display, undo_flash[1],
                 (14, h // 2 - 20), size=36, color=(60, 120, 255), bold=True)
        undo_flash[0] -= 1

    # ── Drag seek readout ─────────────────────────────────────────────────────
    if mouse_state["dragging"] and mouse_state["seek_frame"] is not None:
        sf = mouse_state["seek_frame"]
        put_text(display, f"→ {_sec(sf):.2f}s  (frame {sf})",
                 (14, h // 2 + 30), size=30, color=(80, 200, 255), bold=True)

    # ── Timeline bar ──────────────────────────────────────────────────────────
    draw_timeline(display, current_frame, total_frames, annotations, active, mouse_state)

    # ── Bottom bar ────────────────────────────────────────────────────────────
    shade(display, 0, h - 60, w, h, (15, 15, 15), 0.72)

    guide = "   ".join(f"[{chr(k)}] {v}" for k, v in BEHAVIORS.items())
    put_text(display, guide, (12, h - 54), size=18, color=(200, 200, 200))
    put_text(display,
             f"Total: {len(annotations)} annotations     "
             "SPACE=Play/Pause  Arrow/,.=±1frame  Z/X=±1s  "
             "[U]=Undo  Click/Drag timeline=Seek  Q=Save&Quit",
             (12, h - 28), size=17, color=(150, 150, 150))
