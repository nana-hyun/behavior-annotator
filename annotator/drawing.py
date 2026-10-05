"""
All rendering helpers: font loading, text, timeline bar, and the full overlay.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import BEHAVIORS, COLORS, BAR_H, MARGIN
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

def put_text(
    img_bgr: np.ndarray,
    text: str,
    xy: tuple[int, int],
    size: int = 22,
    color: tuple[int, int, int] = (255, 255, 255),
    bold: bool = False,
) -> None:
    """Render *text* onto a BGR numpy array using PIL (supports system fonts)."""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw    = ImageDraw.Draw(pil_img)
    font    = get_font(size)
    x, y    = xy
    r, g, b = color
    if bold:
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=(r, g, b))
    img_bgr[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


# ── Frame composition ─────────────────────────────────────────────────────────

def compose_display(
    frame1: np.ndarray,
    frame2: np.ndarray | None,
    disp_w: int,
    disp_h: int,
    dual: bool,
) -> np.ndarray:
    """
    Compose the final display canvas.

    In dual mode the two frames are placed side by side with camera labels
    ("TOP" / "FRONT") and a thin divider line.
    """
    if not dual or frame2 is None:
        return frame1.copy()

    canvas = np.hstack([frame1, frame2])

    half = disp_w // 2
    for x_off, label in [(8, "TOP"), (half + 8, "FRONT")]:
        ov = canvas.copy()
        tw = len(label) * 16 + 16
        cv2.rectangle(ov, (x_off - 4, 4), (x_off + tw, 32), (10, 10, 10), -1)
        cv2.addWeighted(ov, 0.55, canvas, 0.45, 0, canvas)
        put_text(canvas, label, (x_off + 4, 8), size=20, color=(200, 200, 200), bold=True)

    cv2.line(canvas, (half, 0), (half, disp_h), (60, 60, 60), 1)
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
    ov = display.copy()
    cv2.rectangle(ov, (0, top - 2), (w, top + BAR_H + 2), (10, 10, 10), -1)
    cv2.addWeighted(ov, 0.72, display, 0.28, 0, display)

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
        ov2 = display.copy()
        cv2.rectangle(ov2, (x1, top + 1), (x2, top + BAR_H - 1), col_cv, -1)
        cv2.addWeighted(ov2, blink, display, 1 - blink, 0, display)

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
    ov = display.copy()
    cv2.rectangle(ov, (0, 0), (w, 56), (15, 15, 15), -1)
    cv2.addWeighted(ov, 0.7, display, 0.3, 0, display)

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
    ov4 = display.copy()
    cv2.rectangle(ov4, (0, h - 60), (w, h), (15, 15, 15), -1)
    cv2.addWeighted(ov4, 0.72, display, 0.28, 0, display)

    guide = "   ".join(f"[{chr(k)}] {v}" for k, v in BEHAVIORS.items())
    put_text(display, guide, (12, h - 54), size=18, color=(200, 200, 200))
    put_text(display,
             f"Total: {len(annotations)} annotations     "
             "SPACE=Play/Pause  Arrow/,.=±1frame  Z/X=±1s  "
             "[U]=Undo  Click/Drag timeline=Seek  Q=Save&Quit",
             (12, h - 28), size=17, color=(150, 150, 150))
