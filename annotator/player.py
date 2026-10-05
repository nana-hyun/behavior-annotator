"""
Player — the main annotation session.

Dual view
---------
The FRONT video is the master: frame numbers, seconds and the CSV file name
all come from the front video.  The TOP video is shown next to it for
reference only and is time-stretched by a fixed rate::

    top_frame = round(front_frame × N_top / N_front)

(The top camera delivered fewer frames for the same recording period, so some
top frames are shown twice.)  Nothing is re-encoded.

Sync points
-----------
The plain rate assumes both cameras started on the same instant and dropped
frames evenly.  If the start (or middle) is off, pause on a moment visible in
both views, shift the top view with [ ] (±1 frame) or { } (±10 frames) until
it matches, and press K to lock a sync point.  The mapping then runs
piece-wise linearly through all sync points and the (fixed) last frame.
Sync points are stored in ``<front>_sync.json`` next to the front video.
Shift+K removes the sync point nearest the current frame.

Single view
-----------
The only video is the master.
"""

from __future__ import annotations

import json
import os
import time
import cv2
import numpy as np

from .config import BEHAVIORS, SINGLE_DISP_W, DUAL_PER_W, TOP_PAD, BOT_PAD
from .drawing import compose_display, draw_overlay
from .mouse import make_mouse_callback, make_mouse_state
from .storage import csv_path_for, load_csv, order_top_front, save_csv

_WIN_TITLE = "Behavior Annotator  |  Q = Save & Quit"

# Arrow-key codes returned by cv2.waitKeyEx() on each GUI backend.
# (cv2.waitKey() & 0xFF turns Windows arrows into 0, which is why they did nothing.)
_LEFT  = {2424832, 65361, 63234, 0x1000012}   # Windows, GTK, macOS, Qt
_RIGHT = {2555904, 65363, 63235, 0x1000014}


class Player:
    """
    Parameters
    ----------
    top_path : str
        Top-view video (or the only video in single-view mode).
    front_path : str | None
        Front-view video.  When given, it becomes the master clock.
    """

    def __init__(self, top_path: str, front_path: str | None = None) -> None:
        if front_path:
            top_path, front_path = order_top_front(top_path, front_path)
        top_cap = self._open_cap(top_path, required=True)
        front_cap = self._open_cap(front_path, required=False) if front_path else None
        self.dual = front_cap is not None

        if self.dual:
            # master = front, reference = top
            self.master_path, self.ref_path = front_path, top_path
            self._cap_m, self._cap_r = front_cap, top_cap
        else:
            self.master_path, self.ref_path = top_path, None
            self._cap_m, self._cap_r = top_cap, None

        self.fps          = self._cap_m.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self._cap_m.get(cv2.CAP_PROP_FRAME_COUNT))

        self._nudge = 0                                   # live top shift (frames)
        self._sync_pts: list[tuple[int, int]] = []        # (front, top) pairs
        self._sync_path = os.path.splitext(self.master_path)[0] + "_sync.json"
        if self.dual:
            self._ref_total = int(self._cap_r.get(cv2.CAP_PROP_FRAME_COUNT))
            self._rate = self._ref_total / max(1, self.total_frames)
            print(f"  [player] Master = FRONT ({self.total_frames} frames), "
                  f"top = {self._ref_total} frames → top stretched by rate "
                  f"{self._rate:.4f}")
            self._load_sync()
        else:
            self._ref_total = 0
            self._rate = 1.0

        vid_w = int(self._cap_m.get(cv2.CAP_PROP_FRAME_WIDTH))
        vid_h = int(self._cap_m.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.dual:
            self._per_w, self._disp_w = DUAL_PER_W, DUAL_PER_W * 2
        else:
            self._per_w, self._disp_w = SINGLE_DISP_W, SINGLE_DISP_W
        self._vid_h  = int(self._per_w * vid_h / vid_w)
        self._disp_h = TOP_PAD + self._vid_h + BOT_PAD

        self._csv_path  = csv_path_for(self.master_path)
        self._playing   = False
        self._play_t0   = 0.0                             # wall clock at play start
        self._play_f0   = 0                               # frame at play start
        self._frame_idx = 0
        self._active: dict[str, int] = {}
        self._undo_flash = [0, ""]
        self._mouse      = make_mouse_state()

        # Playback accumulator for the reference (top) video: last top frame read
        # and its image, so repeated top frames are reused instead of re-seeking.
        self._ref_read_idx: int = -1
        self._last_ref: np.ndarray | None = None

        self._annotations = self._load_existing()
        if self._sync_pts:
            self._refresh_top_columns()

    # ── Setup ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _open_cap(path: str, required: bool) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            msg = f"Cannot open video: {path}"
            if required:
                raise RuntimeError(msg)
            print(f"  [player] Warning: {msg} — running single-view mode.")
            return None
        return cap

    def _load_existing(self) -> list[dict]:
        annotations = load_csv(self._csv_path)

        # One-time migration: an older CSV named after the TOP video with
        # top-frame numbers → convert to front frames and save as the front CSV.
        if not annotations and self.dual:
            old_path = csv_path_for(self.ref_path)
            old = load_csv(old_path)
            if old:
                inv = self.total_frames / max(1, self._ref_total)
                annotations = [
                    self._make_row(a["behavior"],
                                   round(int(a["start_frame"]) * inv),
                                   round(int(a["end_frame"]) * inv))
                    for a in old
                ]
                print(f"  [player] Converted {len(annotations)} annotations from "
                      f"{os.path.basename(old_path)} (top frames) → front frames.  "
                      f"Old file left untouched.")
                save_csv(self._csv_path, annotations)

        if annotations:
            last_frame = max(int(a["end_frame"]) for a in annotations)
            self._frame_idx = min(last_frame, self.total_frames - 1)
            self._seek_both(self._frame_idx)
            print(f"  [player] Resumed: {len(annotations)} annotations, "
                  f"seeked to frame {self._frame_idx} "
                  f"({self._frame_to_sec(self._frame_idx):.1f}s)")
        return annotations

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _frame_to_sec(self, frame: int) -> float:
        return round(frame / self.fps, 3)

    # ── Front → top mapping ───────────────────────────────────────────────────

    def _knots(self) -> tuple[list[int], list[int]]:
        """Sync points + the fixed last-frame pair, sorted by front frame."""
        last = (self.total_frames - 1, self._ref_total - 1)
        pts = dict(self._sync_pts)
        pts.setdefault(last[0], last[1])
        xs = sorted(pts)
        return xs, [pts[x] for x in xs]

    def _ref_frame(self, frame: int, live: bool = True) -> int:
        """
        Master (front) frame → reference (top) frame.

        live=True  : includes the temporary [ ] shift (what is on screen now).
        live=False : locked mapping only (rate + sync points) — used for the CSV.
        """
        if not self._sync_pts:
            y = frame * self._rate                         # plain rate
        else:
            xs, ys = self._knots()
            if len(xs) == 1 or frame <= xs[0]:
                # before the first sync point: same slope as the first segment
                slope = ((ys[1] - ys[0]) / (xs[1] - xs[0])) if len(xs) > 1 else self._rate
                y = ys[0] + (frame - xs[0]) * slope
            else:
                y = float(np.interp(frame, xs, ys))
        shift = self._nudge if live else 0
        return min(max(round(y) + shift, 0), self._ref_total - 1)

    def _load_sync(self) -> None:
        if not os.path.exists(self._sync_path):
            return
        try:
            with open(self._sync_path, encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("top") == os.path.basename(self.ref_path):
                self._sync_pts = [(int(f), int(t)) for f, t in d.get("points", [])]
                print(f"  [player] Loaded {len(self._sync_pts)} sync point(s) "
                      f"from {os.path.basename(self._sync_path)}")
        except Exception as exc:
            print(f"  [player] Could not read {self._sync_path}: {exc}")

    def _save_sync(self) -> None:
        d = {"top": os.path.basename(self.ref_path),
             "front": os.path.basename(self.master_path),
             "points": sorted(self._sync_pts)}
        with open(self._sync_path, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)

    def _flash(self, msg: str, n: int = 40) -> None:
        print(f"  {msg}")
        self._undo_flash[:] = [n, msg]

    def _shift_top(self, delta: int) -> None:
        self._nudge += delta
        self._flash(f"Top shift {self._nudge:+d} fr ({self._nudge / self.fps:+.2f}s)"
                    f"  -  K to lock")
        self._seek_both(self._frame_idx)

    def _lock_sync(self) -> None:
        f, t = self._frame_idx, self._ref_frame(self._frame_idx)
        new = {**dict(self._sync_pts), f: t}
        xs = sorted(new)
        ys = [new[x] for x in xs]
        last_t = self._ref_total - 1
        if any(b <= a for a, b in zip(ys, ys[1:])) or (
                xs[-1] < self.total_frames - 1 and ys[-1] >= last_t):
            self._flash("Sync point rejected: would run the top video backwards", 60)
            return
        self._sync_pts = sorted(new.items())
        self._nudge = 0
        self._save_sync()
        self._refresh_top_columns()
        self._flash(f"Sync point locked: front {f} = top {t}  "
                    f"({len(self._sync_pts)} total)", 60)

    def _delete_nearest_sync(self) -> None:
        if not self._sync_pts:
            self._flash("No sync points")
            return
        f, t = min(self._sync_pts, key=lambda p: abs(p[0] - self._frame_idx))
        self._sync_pts.remove((f, t))
        self._save_sync()
        self._refresh_top_columns()
        self._flash(f"Removed sync point front {f} = top {t}  "
                    f"({len(self._sync_pts)} left)", 60)
        self._seek_both(self._frame_idx)

    def _refresh_top_columns(self) -> None:
        """Mapping changed → recompute the reference top-frame columns."""
        if not self.dual or not self._annotations:
            return
        for a in self._annotations:
            a["start_top_frame"] = self._ref_frame(int(a["start_frame"]), live=False)
            a["end_top_frame"]   = self._ref_frame(int(a["end_frame"]), live=False)
        self._save()

    def _make_row(self, beh: str, start_f: int, end_f: int) -> dict:
        row = {
            "behavior":     beh,
            "start_frame":  int(start_f),
            "start_sec":    self._frame_to_sec(start_f),
            "end_frame":    int(end_f),
            "end_sec":      self._frame_to_sec(end_f),
            "duration_sec": self._frame_to_sec(end_f - start_f),
        }
        if self.dual:
            row["start_top_frame"] = self._ref_frame(start_f, live=False)
            row["end_top_frame"]   = self._ref_frame(end_f, live=False)
        return row

    def _seek_both(self, frame: int) -> None:
        self._cap_m.set(cv2.CAP_PROP_POS_FRAMES, frame)
        # restart the playback clock from here
        self._play_t0, self._play_f0 = time.perf_counter(), frame
        if self._cap_r:
            rf = self._ref_frame(frame)
            self._cap_r.set(cv2.CAP_PROP_POS_FRAMES, rf)
            # next read() yields rf; mark rf-1 so playback reads exactly one frame
            self._ref_read_idx = rf - 1
            self._last_ref = None

    def _read_frame(self, cap: cv2.VideoCapture) -> np.ndarray:
        ret, frame = cap.read()
        if not ret:
            return np.zeros((self._vid_h, self._per_w, 3), dtype=np.uint8)
        return cv2.resize(frame, (self._per_w, self._vid_h))

    def _read_ref_sequential(self) -> np.ndarray:
        """Top frame for the current master frame without seeking."""
        target = self._ref_frame(self._frame_idx)
        n = target - self._ref_read_idx
        if n > 0:
            for _ in range(n - 1):                      # skipped: decode only
                self._cap_r.grab()
            img = self._read_frame(self._cap_r)
            self._ref_read_idx = target
            self._last_ref = img
        elif self._last_ref is None:                    # safety: no frame cached
            self._cap_r.set(cv2.CAP_PROP_POS_FRAMES, target)
            self._last_ref = self._read_frame(self._cap_r)
            self._ref_read_idx = target
        return self._last_ref                           # repeated top frame

    def _save(self) -> None:
        save_csv(self._csv_path, self._annotations)

    # ── Annotation actions ────────────────────────────────────────────────────

    def _toggle_behavior(self, beh: str) -> None:
        if beh in self._active:
            start_f = self._active.pop(beh)
            row = self._make_row(beh, start_f, self._frame_idx)
            self._annotations.append(row)
            print(f"  END   {beh:12s}| "
                  f"{row['start_sec']:.2f}s → "
                  f"{row['end_sec']:.2f}s ({row['duration_sec']}s)")
            self._save()
        else:
            self._active[beh] = self._frame_idx
            print(f"  START {beh:12s}| {self._frame_to_sec(self._frame_idx):.2f}s")

    def _undo(self) -> None:
        if self._annotations:
            removed = self._annotations.pop()
            msg = (f"UNDO: {removed['behavior']}  "
                   f"({removed['start_sec']:.1f}s → {removed['end_sec']:.1f}s)")
            print(f"  {msg}")
            self._undo_flash[:] = [45, msg]
            self._save()
        else:
            self._undo_flash[:] = [30, "Nothing to undo"]

    def _close_active_on_quit(self) -> None:
        for beh, start_f in self._active.items():
            self._annotations.append(self._make_row(beh, start_f, self._frame_idx))

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Open the annotation window and block until the user quits."""
        if self.dual:
            print(f"  Master (front): {os.path.basename(self.master_path)}")
            print(f"  Reference (top): {os.path.basename(self.ref_path)}")
        else:
            print(f"  Video    : {os.path.basename(self.master_path)}")
        print(f"  FPS      : {self.fps:.2f}  |  Frames: {self.total_frames}")
        print(f"  CSV      : {self._csv_path}")

        cv2.namedWindow(_WIN_TITLE, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(_WIN_TITLE, self._disp_w, self._disp_h)
        cv2.setMouseCallback(
            _WIN_TITLE,
            make_mouse_callback(self._mouse, self._disp_w, self._disp_h, self.total_frames),
        )

        while True:
            # ── Mouse seek ────────────────────────────────────────────────────
            if self._mouse["seek_frame"] is not None and not self._mouse["dragging"]:
                self._frame_idx = self._mouse["seek_frame"]
                self._mouse["seek_frame"] = None
                self._seek_both(self._frame_idx)
                self._playing = False

            if self._mouse["dragging"] and self._mouse["seek_frame"] is not None:
                self._frame_idx = self._mouse["seek_frame"]
                self._seek_both(self._frame_idx)

            # ── Frame read ────────────────────────────────────────────────────
            if self._playing:
                # Real-time pacing: if drawing fell behind the wall clock, skip
                # frames (grab only) so the on-screen time keeps real speed.
                due = self._play_f0 + int((time.perf_counter() - self._play_t0) * self.fps)
                behind = due - (self._frame_idx + 1)
                for _ in range(min(max(behind, 0), 10)):
                    self._cap_m.grab()
                ret, raw = self._cap_m.read()
                if not ret:
                    self._playing = False
                    self._frame_idx = min(self._frame_idx, self.total_frames - 1)
                    self._seek_both(self._frame_idx)
                    continue
                self._frame_idx = int(self._cap_m.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                if behind > 10:                         # far behind: restart clock
                    self._play_t0 = time.perf_counter()
                    self._play_f0 = self._frame_idx
                master = cv2.resize(raw, (self._per_w, self._vid_h))
                ref = self._read_ref_sequential() if self._cap_r else None
            else:
                self._seek_both(self._frame_idx)
                ret, raw = self._cap_m.read()
                if not ret:
                    break
                master = cv2.resize(raw, (self._per_w, self._vid_h))
                if self._cap_r:
                    ref = self._read_frame(self._cap_r)
                    self._ref_read_idx = self._ref_frame(self._frame_idx)
                    self._last_ref = ref
                else:
                    ref = None

            # Layout: TOP (reference) on the left, FRONT (master) on the right.
            if self.dual:
                labels = (f"TOP  frame {self._ref_frame(self._frame_idx)}",
                          f"FRONT  frame {self._frame_idx}")
                display = compose_display(ref, master, self._disp_w, self._disp_h,
                                          True, labels)
            else:
                display = compose_display(master, None, self._disp_w, self._disp_h, False)
            draw_overlay(
                display,
                self._frame_idx, self.total_frames, self.fps,
                self._playing, self._active, self._annotations,
                self._undo_flash, self._mouse,
            )
            cv2.imshow(_WIN_TITLE, display)

            if self._playing:
                # wait until the next frame is due (keeps 1× speed on fast PCs)
                next_t = self._play_t0 + (self._frame_idx + 1 - self._play_f0) / self.fps
                wait_ms = min(100, max(1, int((next_t - time.perf_counter()) * 1000)))
            else:
                wait_ms = 8 if self._mouse["dragging"] else 20
            raw_key = cv2.waitKeyEx(wait_ms)
            if raw_key in _LEFT:
                key = "LEFT"
            elif raw_key in _RIGHT:
                key = "RIGHT"
            else:
                key = raw_key & 0xFF if 0 <= raw_key < 0x10000 else -1

            # ── Key handling ──────────────────────────────────────────────────
            if key in (ord("q"), 27):                          # quit
                self._close_active_on_quit()
                self._save()
                break

            elif key == ord(" "):                              # play / pause
                self._playing = not self._playing
                if self._playing:
                    self._seek_both(self._frame_idx)

            elif key in ("LEFT", ord(",")):                    # ← / , : -1 frame
                self._playing = False
                self._frame_idx = max(0, self._frame_idx - 1)

            elif key in ("RIGHT", ord(".")):                   # → / . : +1 frame
                self._playing = False
                self._frame_idx = min(self.total_frames - 1, self._frame_idx + 1)

            elif key == ord("z"):                              # Z : -1 second
                self._frame_idx = max(0, self._frame_idx - int(self.fps))

            elif key == ord("x"):                              # X : +1 second
                self._frame_idx = min(self.total_frames - 1, self._frame_idx + int(self.fps))

            elif key == ord("u"):                              # undo
                self._undo()

            elif self.dual and key in (ord("["), ord("]"), ord("{"), ord("}")):
                step = {ord("["): -1, ord("]"): 1, ord("{"): -10, ord("}"): 10}[key]
                self._shift_top(step)                       # shift top view

            elif self.dual and key == ord("k"):            # lock sync point
                self._lock_sync()

            elif self.dual and key == ord("K"):            # remove nearest point
                self._delete_nearest_sync()

            elif key in BEHAVIORS:                             # behavior toggle
                self._toggle_behavior(BEHAVIORS[key])

        self._cap_m.release()
        if self._cap_r:
            self._cap_r.release()
        cv2.destroyAllWindows()
        print("Finished.")
