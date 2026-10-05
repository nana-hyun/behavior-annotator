"""
Behavior definitions, color palette, and display constants.
"""

# Key → behavior name mapping
BEHAVIORS: dict[int, str] = {
    ord('a'): 'Attack',
    ord('s'): 'Sniffing',
    ord('c'): 'Chase',
    ord('g'): 'Grooming',
    ord('m'): 'Mounting',
    ord('f'): 'Follow',
    ord('e'): 'Escape',
}

# Behavior → RGB color (for overlay and timeline)
COLORS: dict[str, tuple[int, int, int]] = {
    'Attack':   (255,  80,  80),
    'Sniffing': (255, 165,  80),
    'Chase':    (255, 255,  80),
    'Grooming': ( 80, 210,  80),
    'Mounting': (255, 200,  50),
    'Follow':   ( 80, 160, 255),
    'Escape':   ( 80, 220, 200),
}

# Reverse lookup: behavior name → shortcut character
KEY_LABEL: dict[str, str] = {v: chr(k) for k, v in BEHAVIORS.items()}

# ── Display geometry ──────────────────────────────────────────────────────────
SINGLE_DISP_W = 1280   # window width in single-video mode
DUAL_PER_W    = 800    # per-panel width in dual-video mode  (total = 1600)

# Timeline bar
BAR_H  = 18   # height of the timeline bar (px)
MARGIN = 6    # left/right margin of the bar (px)
