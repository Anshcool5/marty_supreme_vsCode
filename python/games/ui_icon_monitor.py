#!/usr/bin/env python3
"""
Screen-region icon state monitor.

Detects two UI icon templates inside a configured screen region:
- thinking icon (stop button)
- ready icon (arrow/send button)

Outputs line-delimited JSON state messages to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass

import cv2
import mss
import numpy as np


@dataclass
class Scores:
    ready: float
    thinking: float


_running = True


def _handle_stop(_sig, _frame):
    global _running
    _running = False


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


def _load_template(path: str, label: str) -> np.ndarray:
    template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"Failed to load {label} template: {path}")
    if template.shape[0] < 4 or template.shape[1] < 4:
        raise RuntimeError(f"Template too small for {label}: {path}")
    return template


def _match_score(region_gray: np.ndarray, template: np.ndarray) -> float:
    if (
        template.shape[0] > region_gray.shape[0]
        or template.shape[1] > region_gray.shape[1]
    ):
        return -1.0

    result = cv2.matchTemplate(region_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def _emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def _create_video_writer(output_path: str, width: int, height: int, fps: float):
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    ext = os.path.splitext(output_path)[1].lower()
    candidates = []
    if ext == ".avi":
        candidates = [("MJPG", output_path), ("XVID", output_path)]
    else:
        candidates = [("mp4v", output_path), ("avc1", output_path), ("H264", output_path)]
        fallback_avi = os.path.splitext(output_path)[0] + ".avi"
        candidates.extend([("MJPG", fallback_avi), ("XVID", fallback_avi)])

    for fourcc_name, path_candidate in candidates:
        fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
        writer = cv2.VideoWriter(path_candidate, fourcc, fps, (width, height))
        if writer.isOpened():
            return writer, path_candidate
        writer.release()

    return None, output_path


def interactive_select(args: argparse.Namespace) -> int:
    with mss.mss() as sct:
        monitor = sct.monitors[args.monitor_index]
        shot = np.array(sct.grab(monitor), dtype=np.uint8)
        frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)

    window_name = "Marty Supreme ROI Picker - Draw box and press ENTER"
    roi = cv2.selectROI(window_name, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()

    x, y, w, h = roi
    if w <= 0 or h <= 0:
        _emit({"type": "roi_cancelled"})
        return 2

    global_x = int(monitor["left"] + x)
    global_y = int(monitor["top"] + y)
    _emit(
        {
            "type": "roi_selected",
            "x": global_x,
            "y": global_y,
            "width": int(w),
            "height": int(h),
            "monitorLeft": int(monitor["left"]),
            "monitorTop": int(monitor["top"]),
        }
    )
    return 0


def _classify(scores: Scores, threshold: float) -> str:
    if scores.ready < threshold and scores.thinking < threshold:
        return "unknown"
    if scores.ready >= scores.thinking:
        return "ready"
    return "thinking"


def monitor(args: argparse.Namespace) -> int:
    ready_template = _load_template(args.ready_icon, "ready")
    thinking_template = _load_template(args.thinking_icon, "thinking")

    region = {
        "top": args.y,
        "left": args.x,
        "width": args.width,
        "height": args.height,
    }

    stable_state = "unknown"
    candidate_state = "unknown"
    candidate_count = 0
    last_heartbeat = 0.0

    _emit(
        {
            "type": "monitor_started",
            "region": region,
            "threshold": args.threshold,
            "intervalMs": args.interval_ms,
            "stableFrames": args.stable_frames,
        }
    )

    writer = None
    started_at = time.time()
    preview_seconds = max(0.0, float(args.preview_seconds))
    preview_mode = preview_seconds > 0.0

    if preview_mode:
        if not args.preview_output:
            raise RuntimeError("--preview-output is required when --preview-seconds is set")

        writer, resolved_path = _create_video_writer(
            args.preview_output,
            args.width,
            args.height,
            1000.0 / max(1, args.interval_ms),
        )
        if writer is None:
            raise RuntimeError(f"Failed to open preview output video: {args.preview_output}")
        args.preview_output = resolved_path

        _emit(
            {
                "type": "preview_started",
                "previewOutput": args.preview_output,
                "previewSeconds": preview_seconds,
            }
        )

    with mss.mss() as sct:
        while _running:
            shot = np.array(sct.grab(region), dtype=np.uint8)
            gray = cv2.cvtColor(shot, cv2.COLOR_BGRA2GRAY)

            scores = Scores(
                ready=_match_score(gray, ready_template),
                thinking=_match_score(gray, thinking_template),
            )
            state = _classify(scores, args.threshold)

            if state != candidate_state:
                candidate_state = state
                candidate_count = 1
            else:
                candidate_count += 1

            if candidate_count >= args.stable_frames and stable_state != candidate_state:
                stable_state = candidate_state
                _emit(
                    {
                        "type": "state",
                        "state": stable_state,
                        "readyScore": scores.ready,
                        "thinkingScore": scores.thinking,
                    }
                )

            now = time.time()
            if now - last_heartbeat > 3.0:
                _emit(
                    {
                        "type": "heartbeat",
                        "state": stable_state,
                        "readyScore": scores.ready,
                        "thinkingScore": scores.thinking,
                    }
                )
                last_heartbeat = now

            if writer is not None:
                frame_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                cv2.putText(
                    frame_bgr,
                    f"state={stable_state} r={scores.ready:.3f} t={scores.thinking:.3f}",
                    (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                writer.write(frame_bgr)

                if preview_mode and (now - started_at) >= preview_seconds:
                    break

            time.sleep(args.interval_ms / 1000.0)

    if writer is not None:
        writer.release()
        _emit(
            {
                "type": "preview_saved",
                "previewOutput": args.preview_output,
            }
        )

    _emit({"type": "monitor_stopped"})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--x", type=int, default=-1)
    parser.add_argument("--y", type=int, default=-1)
    parser.add_argument("--width", type=int, default=-1)
    parser.add_argument("--height", type=int, default=-1)
    parser.add_argument("--thinking-icon", default="")
    parser.add_argument("--ready-icon", default="")
    parser.add_argument("--threshold", type=float, default=0.74)
    parser.add_argument("--interval-ms", type=int, default=120)
    parser.add_argument("--stable-frames", type=int, default=3)
    parser.add_argument("--preview-seconds", type=float, default=0.0)
    parser.add_argument("--preview-output", default="")
    parser.add_argument("--interactive-select", action="store_true")
    parser.add_argument("--monitor-index", type=int, default=0)
    args = parser.parse_args()

    if args.interactive_select:
        try:
            return interactive_select(args)
        except Exception as err:
            print(f"ui_icon_monitor interactive_select error: {err}", file=sys.stderr)
            return 1

    if args.width <= 0 or args.height <= 0 or args.x < 0 or args.y < 0:
        print("Invalid monitor region values.", file=sys.stderr)
        return 2
    if not args.thinking_icon or not args.ready_icon:
        print("Missing icon template paths.", file=sys.stderr)
        return 2

    try:
        return monitor(args)
    except Exception as err:
        print(f"ui_icon_monitor error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
