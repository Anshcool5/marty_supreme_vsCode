#!/usr/bin/env python3
"""
Hand tracking server for Marty Supreme ping pong webview.
Streams normalized paddle position over WebSocket.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass

import cv2
import numpy as np
import websockets

MEDIAPIPE_IMPORT_ERROR = ""
try:
    import mediapipe as mp  # Optional for more robust tracking
    HAS_MEDIAPIPE = True
except Exception as err:
    HAS_MEDIAPIPE = False
    MEDIAPIPE_IMPORT_ERROR = str(err)


@dataclass
class HandState:
    paddle_x: float = 0.5
    paddle_y: float = 0.5
    confidence: float = 0.0
    mode: str = "idle"
    ok: bool = True
    error: str = ""


class HandTracker:
    def __init__(self, camera_index: int = 0, show_preview: bool = False):
        self.state = HandState()
        self._camera_index = camera_index
        self._show_preview = show_preview
        self._smooth_x = 0.5
        self._smooth_y = 0.5
        self._smooth_alpha = 0.22
        self._max_step = 0.09
        self._dead_zone = 0.004
        self._cap = None
        self._hands = None
        self._drawing = None
        self._mp_hands = None

    def open(self) -> None:
        if HAS_MEDIAPIPE:
            self._mp_hands = mp.solutions.hands
            self._drawing = mp.solutions.drawing_utils

        self._cap = cv2.VideoCapture(self._camera_index)
        if not self._cap.isOpened():
            self._update(ok=False, error="Could not open webcam", mode="error")
            return

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if HAS_MEDIAPIPE:
            self._hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.55,
            )

    def close(self) -> None:
        if self._hands:
            self._hands.close()
            self._hands = None
        if self._cap:
            self._cap.release()
            self._cap = None
        if self._show_preview:
            cv2.destroyAllWindows()

    def snapshot(self) -> dict:
        return {
            "paddleX": self.state.paddle_x,
            "paddleY": self.state.paddle_y,
            "confidence": self.state.confidence,
            "mode": self.state.mode,
            "ok": self.state.ok,
            "error": self.state.error,
        }

    def _update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self.state, key, value)

    def _stabilize_target(self, x_norm: float, y_norm: float) -> tuple[float, float]:
        dx = x_norm - self._smooth_x
        dy = y_norm - self._smooth_y
        dist = float((dx * dx + dy * dy) ** 0.5)

        if dist < self._dead_zone:
            return self._smooth_x, self._smooth_y

        if dist > self._max_step and dist > 0:
            scale = self._max_step / dist
            x_norm = self._smooth_x + (dx * scale)
            y_norm = self._smooth_y + (dy * scale)

        return x_norm, y_norm

    def _set_detected(self, x_norm: float, y_norm: float, confidence: float, mode: str) -> None:
        x_norm = float(np.clip(x_norm, 0.0, 1.0))
        y_norm = float(np.clip(y_norm, 0.0, 1.0))
        x_norm, y_norm = self._stabilize_target(x_norm, y_norm)

        alpha = self._smooth_alpha if confidence >= 0.7 else max(0.12, self._smooth_alpha * 0.7)
        self._smooth_x = (1.0 - alpha) * self._smooth_x + alpha * x_norm
        self._smooth_y = (1.0 - alpha) * self._smooth_y + alpha * y_norm
        self._update(
            paddle_x=self._smooth_x,
            paddle_y=self._smooth_y,
            confidence=confidence,
            mode=mode,
            ok=True,
            error="",
        )

    def _set_not_detected(self) -> None:
        next_conf = max(0.0, self.state.confidence - 0.08)
        self._update(confidence=next_conf, ok=True, error="")

    def step(self) -> bool:
        if not self._cap:
            self._update(ok=False, error="Camera not initialized", mode="error")
            return False

        ok, frame = self._cap.read()
        if not ok:
            self._update(ok=False, error="Failed to read webcam frame", mode="error")
            return True

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        detection_found = False
        mode = "idle"

        if self._hands:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._hands.process(rgb)

            if result.multi_hand_landmarks:
                detection_found = True
                mode = "mediapipe_left_palm_y"
                left_idx = None
                left_conf = 0.0

                if result.multi_handedness:
                    for idx, handedness in enumerate(result.multi_handedness):
                        classification = handedness.classification[0]
                        if classification.label == "Left" and classification.score > left_conf:
                            left_idx = idx
                            left_conf = classification.score

                if left_idx is not None:
                    hand_landmarks = result.multi_hand_landmarks[left_idx]
                    landmarks = hand_landmarks.landmark

                    # Left palm center tracking (wrist + palm knuckle bases), Y axis only.
                    palm_ids = [0, 5, 9, 13, 17]
                    palm_center_y = sum(landmarks[i].y for i in palm_ids) / float(len(palm_ids))
                    target_y = palm_center_y
                    target_x = self._smooth_x  # Y-only control for paddle movement.

                    confidence = max(0.65, min(0.99, left_conf if left_conf > 0 else 0.9))
                    self._set_detected(target_x, target_y, confidence=confidence, mode=mode)

                    if self._show_preview and self._drawing:
                        self._drawing.draw_landmarks(
                            frame,
                            hand_landmarks,
                            self._mp_hands.HAND_CONNECTIONS,
                        )
                else:
                    detection_found = False
                    self._set_not_detected()
                    mode = "mediapipe_waiting_left_hand"
            else:
                self._set_not_detected()
                mode = "mediapipe_no_hands"
        else:
            self._set_not_detected()
            mode = "mediapipe_missing"
            self._update(
                ok=False,
                error=(
                    "MediaPipe is required for hand skeleton tracking. "
                    f"Python={sys.executable}. Import error: {MEDIAPIPE_IMPORT_ERROR or 'not installed'}"
                ),
            )

        if self._show_preview:
            snapshot = self.snapshot()
            detection_flag = "TRACKING" if detection_found else "SEARCHING"
            overlay_text = (
                f"{detection_flag} mode={mode} conf={snapshot['confidence']:.2f} "
                f"x={snapshot['paddleX']:.2f} y={snapshot['paddleY']:.2f}"
            )
            cv2.putText(
                frame,
                overlay_text,
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (80, 255, 120) if detection_found else (0, 180, 255),
                2,
                cv2.LINE_AA,
            )
            try:
                cv2.imshow("Marty Supreme Hand Debug", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    return False
            except cv2.error as err:
                self._show_preview = False
                self._update(error=f"Preview disabled: {err}", ok=True)

        return True


async def stream_handler(websocket, tracker: HandTracker):
    while True:
        payload = tracker.snapshot()
        await websocket.send(json.dumps(payload))
        await asyncio.sleep(1 / 30.0)


async def run_server(port: int, camera_index: int, show_preview: bool):
    tracker = HandTracker(camera_index=camera_index, show_preview=show_preview)
    tracker.open()

    print(f"INFO hand_server python={sys.executable}", flush=True)
    if HAS_MEDIAPIPE:
        print("INFO mediapipe=available", flush=True)
    else:
        print(
            f"WARN mediapipe=missing error={MEDIAPIPE_IMPORT_ERROR or 'not installed'}",
            flush=True,
        )
    print(f"INFO hand_server listening ws://127.0.0.1:{port}", flush=True)

    async with websockets.serve(lambda ws: stream_handler(ws, tracker), "127.0.0.1", port, ping_interval=20):
        async def tracking_loop():
            while True:
                should_continue = tracker.step()
                if not should_continue:
                    break
                await asyncio.sleep(1 / 30.0)

        tracking_task = asyncio.create_task(tracking_loop())
        try:
            await tracking_task
        finally:
            tracker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--show-preview", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_server(args.port, args.camera_index, args.show_preview))


if __name__ == "__main__":
    main()