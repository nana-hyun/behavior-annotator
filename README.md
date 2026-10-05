# Behavior Annotator

Frame-accurate behavioral annotation tool for rodent social-behavior videos.  
Built with OpenCV · PIL · pandas.

---

## Features

- **Single or dual-camera view** — display a top-view and front-view side by side, perfectly synchronized
- **Clickable / draggable timeline** — scrub to any position by clicking or dragging the timeline bar
- **Resume support** — re-open a video and pick up where you left off (loads existing CSV automatically)
- **Undo** — remove the last completed annotation instantly
- **Auto-save** — CSV is written after every completed annotation and undo

---

## Behaviors

| Key | Behavior |
|-----|----------|
| `a` | Attack   |
| `s` | Sniffing |
| `c` | Chase    |
| `g` | Grooming |
| `m` | Mounting |
| `f` | Follow   |
| `e` | Escape   |

Each behavior is toggled **on** (first key press) and **off** (second key press).  
Multiple behaviors can be active at the same time.

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
# GUI dialog — prompts for 1 or 2 video files
python annotate.py

# Single-view mode
python annotate.py path/to/top.mp4

# Dual-view mode (top | front, synchronized)
python annotate.py path/to/top.mp4 path/to/front.mp4
```

---

## Controls

| Input | Action |
|-------|--------|
| `Space` | Play / Pause |
| `←` / `,` | −1 frame |
| `→` / `.` | +1 frame |
| `Z` | −1 second |
| `X` | +1 second |
| `U` | Undo last completed annotation |
| Click/drag timeline | Seek to position |
| `Q` / `Esc` | Save & Quit |

---

## Output

Annotations are saved as a CSV file next to the primary video:

```
your_video_annotations.csv
```

| Column | Description |
|--------|-------------|
| `behavior` | Behavior name |
| `start_frame` | Start frame index |
| `start_sec` | Start time (seconds) |
| `end_frame` | End frame index |
| `end_sec` | End time (seconds) |
| `duration_sec` | Duration (seconds) |

---

## Project structure

```
behavior-annotator/
├── annotate.py          # entry point
├── requirements.txt
├── README.md
└── annotator/
    ├── __init__.py
    ├── config.py        # behavior keys, colors, display constants
    ├── storage.py       # CSV load/save, file-picker dialog
    ├── mouse.py         # mouse state, OpenCV callback, geometry helpers
    ├── drawing.py       # font loading, text, timeline, overlay rendering
    └── player.py        # Player class — main session loop
```
