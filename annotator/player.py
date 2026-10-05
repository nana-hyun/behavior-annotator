"""
Player — the main annotation session.

Owns two VideoCapture objects (one optional), the main loop, and all state.
"""

from __future__ import annotations

import os
import cv2
import numpy as np

from .config import BEHAVIORS, SINGLE_DISP_W, DUAL_PER_W
from .drawing import compose_display, draw_overlay
from .mouse import make_mouse_callback, make_mouse_state
from .storage import csv_path_for, load_csv, save_csv

_WIN_TITLE = "Behavior Annotator  |  Q = Save & Quit"


class Player:
    """
    Manages a single annotation session.

    Parameters
    ----------
    path1 : str
        Primary video path (top view, or only video).
    path2 : str | None
        Optional second video path (front view).
    """

    def __init__(self, path1: str, path2: str | None = None) -> None:
        self.path1 = path1
        self.path2 = path2

        self._cap1 = self._open_cap(path1, required=True)
        self._cap2 = self._open_cap(path2, required=False) if path2 else None
        self.dual  = self._cap2 is not None

        self.fps          = self._cap1.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self._cap1.get(cv2.CAP_PROP_FRAME_COUNT))
        if self._cap2:
            self.total_frames = min(
                self.total_frames,
                int(self._cap2.get(cv2.CAP_PROP_FRAME_COUNT)),
            )

        vid_w = int(self._cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
        vid_h = int(self._cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if self.dual:
            self._per_w  = DUAL_PER_W
            self._disp_w = DUAL_PER_W * 2
        else:
            self._per_w  = SINGLE_DISP_W
            self._disp_w = SINGLE_DISP_W

        self._disp_h = int(self._per_w * vid_h / vid_w)

        self._csv_path  = csv_path_for(path1)
        self._playing   = False
        self._frame_idx = 0
        self._active: dict[str, int] = {}
        self._undo_flash = [0, ""]
        self._mouse      = make_mouse_state()

        self._annotations = self._load_existing()

    # ── Setup ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _open_cap(path: str, required: bool) -> cv2.VideoCapture:
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
        if annotations:
            import pandas as pd
            last_frame = max(int(a["end_frame"]) for a in annotations)
            self._frame_idx = min(last_frame, self.total_frames - 1)
            self._seek_both(self._frame_idx)
            print(f"  [player] Resumed: {len(annotations)} annotations, "
                  f"seeked to frame {self._frame_idx} "
                  f"({self._frame_idx / self.fps:.1f}s)")
        return annotations

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _frame_to_sec(self, frame: int) -> float:
        return round(frame / self.fps, 3)

    def _seek_both(self, frame: int) -> None:
        self._cap1.set(cv2.CAP_PROP_POS_FRAMES, frame)
        if self._cap2:
            self._cap2.set(cv2.CAP_PROP_POS_FRAMES, frame)

    def _read_frame(self, cap: cv2.VideoCapture) -> np.ndarray:
        ret, frame = cap.read()
        if not ret:
            return np.zeros((self._disp_h, self._per_w, 3), dtype=np.uint8)
        return cv2.resize(frame, (self._per_w, self._disp_h))

    def _save(self) -> None:
        save_csv(self._csv_path, self._annotations)

    # ── Annotation actions ────────────────────────────────────────────────────

    def _toggle_behavior(self, beh: str) -> None:
        if beh in self._active:
            start_f = self._active.pop(beh)
            end_f   = self._frame_idx
            dur     = round(self._frame_to_sec(end_f - start_f), 3)
            self._annotations.append({
                "behavior":     beh,
                "start_frame":  start_f,
                "start_sec":    self._frame_to_sec(start_f),
                "end_frame":    end_f,
                "end_sec":      self._frame_to_sec(end_f),
                "duration_sec": dur,
            })
            print(f"  END   {beh:12s}| "
                  f"{self._frame_to_sec(start_f):.2f}s → "
                  f"{self._frame_to_sec(end_f):.2f}s ({dur}s)")
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
            end_f = self._frame_idx
            self._annotations.append({
                "behavior":     beh,
                "start_frame":  start_f,
                "start_sec":    self._frame_to_sec(start_f),
                "end_frame":    end_f,
                "end_sec":      self._frame_to_sec(end_f),
                "duration_sec": round(self._frame_to_sec(end_f - start_f), 3),
            })

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Open the annotation window and block until the user quits."""
        print(f"  Primary  : {os.path.basename(self.path1)}")
        if self.dual:
            print(f"  Secondary: {os.path.basename(self.path2)}")
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
                ret, raw = self._cap1.read()
                if not ret:
                    self._playing = False
                    self._frame_idx = min(self._frame_idx, self.total_frames - 1)
                    self._seek_both(self._frame_idx)
                    continue
                self._frame_idx = int(self._cap1.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                frame1 = cv2.resize(raw, (self._per_w, self._disp_h))
                frame2 = self._read_frame(self._cap2) if self._cap2 else None
            else:
                self._seek_both(self._frame_idx)
                ret, raw = self._cap1.read()
                if not ret:
                    break
                frame1 = cv2.resize(raw, (self._per_w, self._disp_h))
                frame2 = self._read_frame(self._cap2) if self._cap2 else None

            display = compose_display(frame1, frame2, self._disp_w, self._disp_h, self.dual)
            draw_overlay(
                display,
                self._frame_idx, self.total_frames, self.fps,
                self._playing, self._active, self._annotations,
                self._undo_flash, self._mouse,
            )
            cv2.imshow(_WIN_TITLE, display)

            wait_ms = 8 if self._mouse["dragging"] else (1 if self._playing else 20)
            key = cv2.waitKey(wait_ms) & 0xFF

            # ── Key handling ──────────────────────────────────────────────────
            if key in (ord("q"), 27):                          # quit
                self._close_active_on_quit()
                self._save()
                break

            elif key == ord(" "):                              # play / pause
                self._playing = not self._playing

            elif key in (81, 2, ord(",")):                     # ← / , : -1 frame
                self._frame_idx = max(0, self._frame_idx - 1)

            elif key in (83, 3, ord(".")):                     # → / . : +1 frame
                self._frame_idx = min(self.total_frames - 1, self._frame_idx + 1)

            elif key == ord("z"):                              # Z : -1 second
                self._frame_idx = max(0, self._frame_idx - int(self.fps))

            elif key == ord("x"):                              # X : +1 second
                self._frame_idx = min(self.total_frames - 1, self._frame_idx + int(self.fps))

            elif key == ord("u"):                              # undo
                self._undo()

            elif key in BEHAVIORS:                             # behavior toggle
                self._toggle_behavior(BEHAVIORS[key])

        self._cap1.release()
        if self._cap2:
            self._cap2.release()
        cv2.destroyAllWindows()
        print("Finished.")
