# Behavior Annotator

Frame-accurate behavioral annotation tool for rodent social-behavior videos.
Built with OpenCV · PIL · pandas.

---

## Features

- **Single or dual-camera view.** Top and front views side by side.
- **Front-view master clock.** In dual mode, frame numbers, seconds and the CSV name come from the front video; the top view is shown for reference.
- **Any file order.** Top/front are detected from the file names (`top` / `front`), so you can pick them in either order.
- **Frame-level sync adjustment.** Shift the top view frame by frame and lock sync points.
- **Clickable / draggable timeline** to scrub to any position.
- **Real-time playback.** Plays at 1× even on slower PCs; frames are skipped if drawing falls behind.
- **Resume, undo, auto-save.** The CSV is written after every completed annotation and undo.

---

## Installation

```bash
pip install -e .          # installs the `annotate` command
# or
pip install -r requirements.txt   # then use `python annotate.py`
```

---

## Usage

```bash
annotate                          # file dialog — pick 1 or 2 videos
annotate video.avi                # single view
annotate top.avi front.avi        # dual view (order doesn't matter)
```

Dual view needs `top` and `front` in the file names, e.g.
`Aggw3_sub03_top_2026-10-01T17_11_40.avi` / `Aggw3_sub03_front_2026-10-01T17_11_40.avi`.
If the names don't tell, the first file is used as TOP and a warning is printed.

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

Press once to start, again to end. Several behaviors can be active at once.

---

## Controls

### Moving through the video

| Input | Action |
|-------|--------|
| `Space` | Play / Pause |
| `←` / `,` | −1 frame (pauses playback) |
| `→` / `.` | +1 frame (pauses playback) |
| `Z` / `X` | −1 / +1 second |
| Click / drag timeline | Seek |
| `U` | Undo last completed annotation |
| `Q` / `Esc` | Save & quit |

### Adjusting top ↔ front sync (dual view)

| Input | Action |
|-------|--------|
| `[` / `]` | Shift top view −1 / +1 frame |
| `{` / `}` | Shift top view −10 / +10 frames |
| `K` | Lock the current alignment as a sync point |
| `Shift+K` | Remove the sync point nearest the current frame |

The current frame of each view is shown in the panel labels
(`TOP  frame 16843` | `FRONT  frame 17977`).

---

## How dual-view sync works

The front video is the master. By default the top view is stretched by a fixed
rate so the first and last frames of both videos line up:

```
top_frame = round(front_frame × N_top / N_front)
```

This assumes both cameras started at the same instant and the top camera
dropped frames evenly. If the start or the middle doesn't line up:

1. Pause on a moment that is clearly visible in both views (e.g. the hand entering the cage).
2. Shift the top view with `[` `]` (1 frame) or `{` `}` (10 frames) until both views match.
3. Press `K` to lock it. The top view now runs piece-wise linearly through all sync points and the last frame.
4. Check a later part of the video. If it's still off, add another sync point there.

Sync points are saved next to the front video as `<front>_sync.json` and are
re-applied the next time the pair is opened. Unlocked shifts (`[` `]` without
`K`) are temporary and are **not** written to the CSV.

Nothing is re-encoded.

---

## Output

Annotations are saved next to the master video (the front view in dual mode):

```
<front video name>_annotations.csv
```

| Column | Description |
|--------|-------------|
| `behavior` | Behavior name |
| `start_frame` / `end_frame` | Frame index in the master (front) video |
| `start_sec` / `end_sec` | `frame / fps` of the master video |
| `duration_sec` | `end_sec − start_sec` |
| `start_top_frame` / `end_top_frame` | Top-video frame index shown at that moment (dual view only; follows the locked sync points) |

An older CSV named after the top video (top-frame indices) is converted
automatically the first time the pair is opened; the old file is kept.

---

## Recording tips (avoiding frame drops)

The `FrameRate` property of Bonsai's `VideoWriter` only labels the file; the
camera decides how many frames actually arrive. If a camera delivers fewer
frames than the label says, the video plays too fast and drifts from the other
camera. To avoid this:

- **Fix the exposure.** Turn off auto-exposure and keep the exposure clearly shorter than 1/fps (≤ 20 ms at 30 fps). Add IR light instead of lengthening exposure.
- **Fix the camera frame rate** (`CaptureProperties` → `Fps` = 30) and turn off any low-light compensation in the camera driver.
- **Spread the USB load.** Plug the cameras into different USB controllers, not the same hub, and request MJPG from webcams so 1280×720 @ 30 fps fits the bandwidth.
- **Log a timestamp per frame** (`Timestamp` → `MemberSelector` → `CsvWriter`) so drops can be detected and corrected exactly.
- **Test before each session.** Record 1 min with both cameras under the real lighting; each file should have ~1800 frames.
- **Best:** hardware-trigger both cameras (and the photometry/ephys system) from one TTL source.

---

## Project structure

```
behavior-annotator/
├── annotate.py          # entry point (python annotate.py)
├── pyproject.toml       # `annotate` / `sync-videos` console scripts
├── requirements.txt
├── README.md
└── annotator/
    ├── __init__.py
    ├── cli.py           # argument parsing
    ├── config.py        # behavior keys, colors, display constants
    ├── storage.py       # CSV load/save, file dialog, top/front detection
    ├── mouse.py         # mouse state, OpenCV callback, geometry helpers
    ├── drawing.py       # text, timeline, overlay rendering
    ├── player.py        # Player — main loop, sync mapping
    ├── sync.py          # legacy `sync-videos` (FFmpeg front→top stretch;
    └── cli_sync.py      #   writes new files, not used by `annotate`)
```
