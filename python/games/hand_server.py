#!/usr/bin/env python3
"""
Hand tracking server for Marty Supreme ping pong webview.
Also supports standalone 1950s-themed Pong via --run-pong.
"""

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass

import cv2
import numpy as np
try:
    from audio_effects import GameAudioEffects
except ImportError:
    from .audio_effects import GameAudioEffects

try:
    import websockets
    HAS_WEBSOCKETS = True
except Exception:
    HAS_WEBSOCKETS = False

try:
    import pygame
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

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
    right_paddle_y: float = 0.5
    right_confidence: float = 0.0
    right_mode: str = "idle"
    ok: bool = True
    error: str = ""


class HandTracker:
    def __init__(self, camera_index: int = 0, show_preview: bool = False):
        self.state = HandState()
        self._camera_index = camera_index
        self._show_preview = show_preview
        self._smooth_x = 0.5
        self._smooth_y = 0.5
        self._smooth_right_y = 0.5
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
            "rightPaddleY": self.state.right_paddle_y,
            "rightConfidence": self.state.right_confidence,
            "rightMode": self.state.right_mode,
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

    def _set_detected_right(self, y_norm: float, confidence: float, mode: str) -> None:
        y_norm = float(np.clip(y_norm, 0.0, 1.0))
        dy = y_norm - self._smooth_right_y
        if abs(dy) > self._max_step:
            y_norm = self._smooth_right_y + np.sign(dy) * self._max_step

        alpha = self._smooth_alpha if confidence >= 0.7 else max(0.12, self._smooth_alpha * 0.7)
        self._smooth_right_y = (1.0 - alpha) * self._smooth_right_y + alpha * y_norm
        self._update(
            right_paddle_y=self._smooth_right_y,
            right_confidence=confidence,
            right_mode=mode,
            ok=True,
            error="",
        )

    def _set_not_detected(self) -> None:
        next_conf = max(0.0, self.state.confidence - 0.08)
        self._update(confidence=next_conf, ok=True, error="")

    def _set_not_detected_right(self) -> None:
        next_conf = max(0.0, self.state.right_confidence - 0.08)
        self._update(right_confidence=next_conf, ok=True, error="")

    def _is_finger_folded(self, lm, tip_idx: int, pip_idx: int) -> bool:
        return lm[tip_idx].y > lm[pip_idx].y

    def _is_fist(self, lm) -> bool:
        folded_four = (
            self._is_finger_folded(lm, 8, 6)
            and self._is_finger_folded(lm, 12, 10)
            and self._is_finger_folded(lm, 16, 14)
            and self._is_finger_folded(lm, 20, 18)
        )
        thumb_not_extended = abs(lm[4].x - lm[2].x) < 0.10
        return folded_four and thumb_not_extended

    def _is_thumbs_up(self, lm) -> bool:
        folded_four = (
            self._is_finger_folded(lm, 8, 6)
            and self._is_finger_folded(lm, 12, 10)
            and self._is_finger_folded(lm, 16, 14)
            and self._is_finger_folded(lm, 20, 18)
        )
        thumb_up = lm[4].y < lm[3].y < lm[2].y
        return folded_four and thumb_up

    def _is_thumbs_down(self, lm) -> bool:
        folded_four = (
            self._is_finger_folded(lm, 8, 6)
            and self._is_finger_folded(lm, 12, 10)
            and self._is_finger_folded(lm, 16, 14)
            and self._is_finger_folded(lm, 20, 18)
        )
        thumb_down = lm[4].y > lm[3].y > lm[2].y
        return folded_four and thumb_down

    def _gesture_target(self, landmarks, current_y: float) -> tuple[str, float]:
        if self._is_thumbs_up(landmarks):
            return "thumbs_up", max(0.0, current_y - 0.06)
        if self._is_thumbs_down(landmarks):
            return "thumbs_down", min(1.0, current_y + 0.06)
        if self._is_fist(landmarks):
            return "fist_hold", current_y
        return "gesture_idle", current_y

    def step(self) -> bool:
        if not self._cap:
            self._update(ok=False, error="Camera not initialized", mode="error")
            return False

        ok, frame = self._cap.read()
        if not ok:
            self._update(ok=False, error="Failed to read webcam frame", mode="error")
            return True

        frame = cv2.flip(frame, 1)
        detection_found = False
        mode = "idle"

        if self._hands:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._hands.process(rgb)

            if result.multi_hand_landmarks:
                detection_found = True
                mode = "mediapipe_tracking"
                left_candidate = None
                right_candidate = None

                handedness_map: dict[int, tuple[str, float]] = {}
                if result.multi_handedness:
                    for idx, handedness in enumerate(result.multi_handedness):
                        classification = handedness.classification[0]
                        handedness_map[idx] = (classification.label, classification.score)

                for idx, hand_landmarks in enumerate(result.multi_hand_landmarks):
                    label, score = handedness_map.get(idx, ("Unknown", 0.5))
                    if label == "Left":
                        if left_candidate is None or score > left_candidate[2]:
                            left_candidate = (idx, hand_landmarks, score)
                    elif label == "Right":
                        if right_candidate is None or score > right_candidate[2]:
                            right_candidate = (idx, hand_landmarks, score)

                if left_candidate is not None:
                    _, hand_landmarks, left_conf = left_candidate
                    landmarks = hand_landmarks.landmark
                    confidence = max(0.65, min(0.99, left_conf if left_conf > 0 else 0.9))
                    left_mode, left_target_y = self._gesture_target(landmarks, self._smooth_y)
                    self._set_detected(self._smooth_x, left_target_y, confidence=confidence, mode=left_mode)
                    if self._show_preview and self._drawing:
                        self._drawing.draw_landmarks(
                            frame,
                            hand_landmarks,
                            self._mp_hands.HAND_CONNECTIONS,
                        )
                else:
                    self._set_not_detected()

                if right_candidate is not None:
                    _, hand_landmarks, right_conf = right_candidate
                    landmarks = hand_landmarks.landmark
                    confidence = max(0.65, min(0.99, right_conf if right_conf > 0 else 0.9))
                    right_mode, right_target_y = self._gesture_target(
                        landmarks, self._smooth_right_y
                    )
                    self._set_detected_right(
                        right_target_y, confidence=confidence, mode=right_mode
                    )
                    if self._show_preview and self._drawing:
                        self._drawing.draw_landmarks(
                            frame,
                            hand_landmarks,
                            self._mp_hands.HAND_CONNECTIONS,
                        )
                else:
                    self._set_not_detected_right()

                if left_candidate is None and right_candidate is None:
                    detection_found = False
                    mode = "mediapipe_waiting_hands"
            else:
                self._set_not_detected()
                self._set_not_detected_right()
                mode = "mediapipe_no_hands"
        else:
            self._set_not_detected()
            self._set_not_detected_right()
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
                f"yL={snapshot['paddleY']:.2f} yR={snapshot['rightPaddleY']:.2f} "
                f"mL={snapshot['mode']} mR={snapshot['rightMode']}"
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


class MartySupremePong1950:
    WIDTH = 980
    HEIGHT = 620
    PADDLE_W = 14
    PADDLE_H = 102
    BALL_SIZE = 14
    MARGIN = 24
    PLAY_TOP = 128
    PLAY_BOTTOM_PAD = 32
    WIN_SCORE = 3

    BG_TOP = (16, 46, 37)
    BG_BOTTOM = (5, 17, 12)
    GOLD = (214, 179, 108)
    IVORY = (244, 234, 207)
    COPPER = (122, 78, 39)

    def __init__(self, camera_index: int = 0, show_preview: bool = False):
        self.camera_index = camera_index
        self.show_preview = show_preview
        self.two_player = False
        self.tracker = HandTracker(camera_index=camera_index, show_preview=show_preview)

        play_bottom = self.HEIGHT - self.PLAY_BOTTOM_PAD
        self.left_y = self.PLAY_TOP + ((play_bottom - self.PLAY_TOP - self.PADDLE_H) / 2)
        self.right_y = self.PLAY_TOP + ((play_bottom - self.PLAY_TOP - self.PADDLE_H) / 2)
        self.ball_x = self.WIDTH / 2
        self.ball_y = (self.PLAY_TOP + (play_bottom - self.BALL_SIZE)) / 2
        self.ball_vx = 14.0
        self.ball_vy = 5.6
        self.left_score = 0
        self.right_score = 0
        self.status = "Choose mode: Single Player or Double Player"
        self.match_over = False
        self.match_result = ""
        self.mode_menu_active = True
        self.audio_effects = None
        self.single_btn = pygame.Rect(self.WIDTH // 2 - 255, 300, 230, 76)
        self.double_btn = pygame.Rect(self.WIDTH // 2 + 25, 300, 230, 76)

    def _center_positions(self) -> None:
        play_bottom = self.HEIGHT - self.PLAY_BOTTOM_PAD
        self.left_y = self.PLAY_TOP + ((play_bottom - self.PLAY_TOP - self.PADDLE_H) / 2)
        self.right_y = self.PLAY_TOP + ((play_bottom - self.PLAY_TOP - self.PADDLE_H) / 2)
        self.ball_x = self.WIDTH / 2
        self.ball_y = (self.PLAY_TOP + (play_bottom - self.BALL_SIZE)) / 2

    def _start_mode(self, two_player: bool) -> None:
        self.two_player = two_player
        self.mode_menu_active = False
        self.left_score = 0
        self.right_score = 0
        self.match_over = False
        self.match_result = ""
        self._center_positions()
        self.status = (
            "Tracking LEFT + RIGHT hands..."
            if self.two_player
            else "Tracking left hand..."
        )
        self._reset_ball(direction=random.choice([-1, 1]))

    def _reset_ball(self, direction: int) -> None:
        self.ball_x = self.WIDTH / 2
        self.ball_y = (self.PLAY_TOP + (self.HEIGHT - self.PLAY_BOTTOM_PAD - self.BALL_SIZE)) / 2
        self.ball_vx = direction * (12.8 + random.random() * 3.8)
        self.ball_vy = random.uniform(-6.8, 6.8)

    def _finish_match(self, result: str) -> None:
        if self.match_over:
            return

        self.match_over = True
        self.match_result = result
        if result == "win":
            self.status = "You won this set. Press R to play again or ESC to quit."
            if self.audio_effects is not None:
                self.audio_effects.play_win()
        else:
            self.status = "You lost this set. Press R to restart or ESC to quit."
            if self.audio_effects is not None:
                self.audio_effects.play_lose()

    def _update_logic(self) -> None:
        if self.match_over:
            return

        play_bottom = self.HEIGHT - self.PLAY_BOTTOM_PAD
        move_speed = 12.4
        gesture = self.tracker.state.mode
        if gesture == "thumbs_up":
            self.left_y -= move_speed
        elif gesture == "thumbs_down":
            self.left_y += move_speed
        elif gesture == "fist_hold":
            pass
        self.left_y = max(self.PLAY_TOP, min(play_bottom - self.PADDLE_H, self.left_y))

        if self.two_player:
            right_gesture = self.tracker.state.right_mode
            if right_gesture == "thumbs_up":
                self.right_y -= move_speed
            elif right_gesture == "thumbs_down":
                self.right_y += move_speed
            elif right_gesture == "fist_hold":
                pass
            self.right_y = max(
                self.PLAY_TOP, min(play_bottom - self.PADDLE_H, self.right_y)
            )
        else:
            ai_center = self.right_y + self.PADDLE_H / 2
            ball_center = self.ball_y + self.BALL_SIZE / 2
            ai_speed = 8.0
            if ball_center < ai_center - 8:
                self.right_y -= ai_speed
            elif ball_center > ai_center + 8:
                self.right_y += ai_speed
            self.right_y = max(self.PLAY_TOP, min(play_bottom - self.PADDLE_H, self.right_y))

        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        if self.ball_y <= self.PLAY_TOP:
            self.ball_y = self.PLAY_TOP
            self.ball_vy = abs(self.ball_vy)
        elif self.ball_y >= play_bottom - self.BALL_SIZE:
            self.ball_y = play_bottom - self.BALL_SIZE
            self.ball_vy *= -1

        left_paddle_x = self.MARGIN
        if (
            self.ball_x <= left_paddle_x + self.PADDLE_W
            and self.ball_y + self.BALL_SIZE >= self.left_y
            and self.ball_y <= self.left_y + self.PADDLE_H
        ):
            self.ball_x = left_paddle_x + self.PADDLE_W
            self.ball_vx = abs(self.ball_vx) + 0.18
            offset = (self.ball_y - (self.left_y + self.PADDLE_H / 2)) / (self.PADDLE_H / 2)
            self.ball_vy = offset * 4.0

        right_paddle_x = self.WIDTH - self.MARGIN - self.PADDLE_W
        if (
            self.ball_x + self.BALL_SIZE >= right_paddle_x
            and self.ball_y + self.BALL_SIZE >= self.right_y
            and self.ball_y <= self.right_y + self.PADDLE_H
        ):
            self.ball_x = right_paddle_x - self.BALL_SIZE
            self.ball_vx = -abs(self.ball_vx) - 0.18
            offset = (self.ball_y - (self.right_y + self.PADDLE_H / 2)) / (self.PADDLE_H / 2)
            self.ball_vy = offset * 4.0

        if self.ball_x < -20:
            self.right_score += 1
            if self.right_score >= self.WIN_SCORE:
                self._finish_match("lose")
            else:
                self._reset_ball(direction=1)

        if self.ball_x > self.WIDTH + 20:
            self.left_score += 1
            if self.left_score >= self.WIN_SCORE:
                self._finish_match("win")
            else:
                self._reset_ball(direction=-1)

        if self.match_over:
            return

        if self.two_player and (
            self.tracker.state.confidence < 0.2
            or self.tracker.state.right_confidence < 0.2
        ):
            self.status = (
                "Show LEFT and RIGHT hands: thumbs up/down move, fist holds"
            )
        elif not self.two_player and self.tracker.state.confidence < 0.2:
            self.status = "Show LEFT hand: thumbs up/down to move, fist to hold"
        else:
            if self.two_player:
                self.status = (
                    f"L={self.tracker.state.mode}({self.tracker.state.confidence:.2f}) "
                    f"R={self.tracker.state.right_mode}({self.tracker.state.right_confidence:.2f}) "
                    "| thumbs up/down move, fist holds"
                )
            else:
                self.status = (
                    f"Gesture={self.tracker.state.mode} "
                    f"conf={self.tracker.state.confidence:.2f} "
                    "| thumbs up/down move, fist holds"
                )

    def _draw(self, screen, fonts) -> None:
        title_font, text_font, small_font = fonts

        for y in range(self.HEIGHT):
            blend = y / float(self.HEIGHT)
            color = (
                int(self.BG_TOP[0] + (self.BG_BOTTOM[0] - self.BG_TOP[0]) * blend),
                int(self.BG_TOP[1] + (self.BG_BOTTOM[1] - self.BG_TOP[1]) * blend),
                int(self.BG_TOP[2] + (self.BG_BOTTOM[2] - self.BG_TOP[2]) * blend),
            )
            pygame.draw.line(screen, color, (0, y), (self.WIDTH, y))

        frame = pygame.Rect(10, 10, self.WIDTH - 20, self.HEIGHT - 20)
        pygame.draw.rect(screen, self.GOLD, frame, width=3, border_radius=12)

        title = title_font.render("MARTY SUPREME PONG 1950", True, self.IVORY)
        screen.blit(title, (self.WIDTH // 2 - title.get_width() // 2, 18))

        status_panel = pygame.Rect(24, 66, self.WIDTH - 48, 42)
        pygame.draw.rect(screen, (19, 65, 49), status_panel, border_radius=8)
        pygame.draw.rect(screen, self.GOLD, status_panel, width=2, border_radius=8)
        status_text = small_font.render(self.status + "  |  ESC to quit", True, self.IVORY)
        screen.blit(status_text, (36, 78))

        for y in range(self.PLAY_TOP, self.HEIGHT - self.PLAY_BOTTOM_PAD, 26):
            pygame.draw.rect(screen, self.GOLD, (self.WIDTH // 2 - 2, y, 4, 14), border_radius=2)

        left_x = self.MARGIN
        right_x = self.WIDTH - self.MARGIN - self.PADDLE_W
        pygame.draw.rect(screen, self.COPPER, (left_x, self.left_y, self.PADDLE_W, self.PADDLE_H), border_radius=6)
        pygame.draw.rect(screen, self.COPPER, (right_x, self.right_y, self.PADDLE_W, self.PADDLE_H), border_radius=6)
        pygame.draw.rect(screen, self.IVORY, (self.ball_x, self.ball_y, self.BALL_SIZE, self.BALL_SIZE), border_radius=3)

        score_left = text_font.render(str(self.left_score), True, self.IVORY)
        score_right = text_font.render(str(self.right_score), True, self.IVORY)
        screen.blit(score_left, (self.WIDTH * 0.25, 118))
        screen.blit(score_right, (self.WIDTH * 0.75, 118))

        if self.match_over:
            banner = pygame.Rect(170, 272, self.WIDTH - 340, 110)
            pygame.draw.rect(screen, (25, 73, 55), banner, border_radius=10)
            pygame.draw.rect(screen, self.GOLD, banner, width=2, border_radius=10)
            if self.match_result == "win":
                title = small_font.render("VICTORY", True, self.IVORY)
            else:
                title = small_font.render("DEFEAT", True, self.IVORY)
            subtitle = small_font.render("Press R to restart set", True, self.IVORY)
            screen.blit(title, (banner.centerx - title.get_width() // 2, banner.y + 26))
            screen.blit(subtitle, (banner.centerx - subtitle.get_width() // 2, banner.y + 58))

    def _draw_mode_menu(self, screen, fonts) -> None:
        title_font, _, small_font = fonts
        mouse_pos = pygame.mouse.get_pos()

        overlay = pygame.Surface((self.WIDTH, self.HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 15, 11, 190))
        screen.blit(overlay, (0, 0))

        menu_panel = pygame.Rect(120, 190, self.WIDTH - 240, 260)
        pygame.draw.rect(screen, (18, 61, 47), menu_panel, border_radius=12)
        pygame.draw.rect(screen, self.GOLD, menu_panel, width=2, border_radius=12)

        heading = title_font.render("SELECT GAME MODE", True, self.IVORY)
        screen.blit(heading, (self.WIDTH // 2 - heading.get_width() // 2, 215))

        hint = small_font.render("Press 1 / 2 or click a button", True, self.IVORY)
        screen.blit(hint, (self.WIDTH // 2 - hint.get_width() // 2, 264))

        single_hover = self.single_btn.collidepoint(mouse_pos)
        double_hover = self.double_btn.collidepoint(mouse_pos)

        single_fill = (39, 114, 86) if single_hover else (27, 84, 64)
        double_fill = (74, 103, 46) if double_hover else (58, 80, 35)

        pygame.draw.rect(screen, single_fill, self.single_btn, border_radius=10)
        pygame.draw.rect(screen, self.GOLD, self.single_btn, width=2, border_radius=10)
        pygame.draw.rect(screen, double_fill, self.double_btn, border_radius=10)
        pygame.draw.rect(screen, self.GOLD, self.double_btn, width=2, border_radius=10)

        single_label = small_font.render("1) SINGLE PLAYER", True, self.IVORY)
        double_label = small_font.render("2) DOUBLE PLAYER", True, self.IVORY)
        single_sub = small_font.render("Left hand vs AI", True, self.IVORY)
        double_sub = small_font.render("Left hand vs Right hand", True, self.IVORY)

        screen.blit(
            single_label,
            (
                self.single_btn.centerx - single_label.get_width() // 2,
                self.single_btn.y + 14,
            ),
        )
        screen.blit(
            single_sub,
            (
                self.single_btn.centerx - single_sub.get_width() // 2,
                self.single_btn.y + 42,
            ),
        )
        screen.blit(
            double_label,
            (
                self.double_btn.centerx - double_label.get_width() // 2,
                self.double_btn.y + 14,
            ),
        )
        screen.blit(
            double_sub,
            (
                self.double_btn.centerx - double_sub.get_width() // 2,
                self.double_btn.y + 42,
            ),
        )

    def run(self) -> int:
        if not HAS_PYGAME:
            print("ERROR pygame is required for --run-pong mode.", file=sys.stderr)
            return 2

        pygame.init()
        pygame.display.set_caption("Marty Supreme Pong 1950")
        screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        clock = pygame.time.Clock()

        title_font = pygame.font.SysFont("georgia", 44, bold=True)
        text_font = pygame.font.SysFont("georgia", 40, bold=True)
        small_font = pygame.font.SysFont("georgia", 22)

        self.tracker.open()
        if not self.tracker.state.ok and self.tracker.state.error:
            pygame.quit()
            print(self.tracker.state.error, file=sys.stderr)
            return 1

        self.audio_effects = GameAudioEffects()
        self.audio_effects.play_boot()

        running = True
        try:
            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        running = False
                    if self.mode_menu_active and event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_1, pygame.K_KP1):
                            self._start_mode(two_player=False)
                        elif event.key in (pygame.K_2, pygame.K_KP2):
                            self._start_mode(two_player=True)
                    if (
                        self.mode_menu_active
                        and event.type == pygame.MOUSEBUTTONDOWN
                        and event.button == 1
                    ):
                        if self.single_btn.collidepoint(event.pos):
                            self._start_mode(two_player=False)
                        elif self.double_btn.collidepoint(event.pos):
                            self._start_mode(two_player=True)
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_r and self.match_over:
                        self._start_mode(two_player=self.two_player)

                should_continue = self.tracker.step()
                if not should_continue:
                    running = False
                    break

                if not self.mode_menu_active:
                    self._update_logic()
                self._draw(screen, (title_font, text_font, small_font))
                if self.mode_menu_active:
                    self._draw_mode_menu(screen, (title_font, text_font, small_font))
                pygame.display.flip()
                clock.tick(60)
        finally:
            self.tracker.close()
            pygame.quit()

        return 0


async def stream_handler(websocket, tracker: HandTracker):
    while True:
        payload = tracker.snapshot()
        await websocket.send(json.dumps(payload))
        await asyncio.sleep(1 / 30.0)


async def run_server(port: int, camera_index: int, show_preview: bool):
    if not HAS_WEBSOCKETS:
        raise RuntimeError("websockets package is required for server mode.")

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

    async with websockets.serve(
        lambda ws: stream_handler(ws, tracker),
        "127.0.0.1",
        port,
        ping_interval=20,
    ):
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
    parser.add_argument("--run-pong", action="store_true")
    args = parser.parse_args()

    if args.run_pong:
        game = MartySupremePong1950(
            camera_index=args.camera_index,
            show_preview=args.show_preview,
        )
        raise SystemExit(game.run())

    asyncio.run(run_server(args.port, args.camera_index, args.show_preview))


if __name__ == "__main__":
    main()
