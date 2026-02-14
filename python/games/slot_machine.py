import pygame
import cv2
import numpy as np
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional, Set
try:
    from audio_effects import GameAudioEffects
except ImportError:
    from .audio_effects import GameAudioEffects

'''
Slot Machine 1950s Vegas
Computer vision-controlled slot machine game with blink and fist motion detection
Created for UAIS SillyCon Valley Hackathon 2026
'''

# Global Constants
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 750
FPS = 60

# 1950s Vegas Neon Color Palette
BG_TOP = (28, 8, 48)              # Deep purple (night sky)
BG_BOTTOM = (12, 4, 20)           # Darker purple
NEON_PINK = (255, 20, 147)        # Hot pink neon
NEON_CYAN = (0, 255, 255)         # Cyan neon
NEON_GOLD = (255, 215, 0)         # Gold
TEXT_CREAM = (255, 253, 208)      # Cream white
REEL_BG = (40, 20, 60)            # Dark purple for reel background
REEL_BORDER = (255, 215, 0)       # Gold borders
PANEL_BG = (32, 16, 48)           # Panel background
ACCENT = (196, 154, 86)           # Bronze accent

# Reel Configuration
REEL_WIDTH = 200
REEL_HEIGHT = 300
SYMBOL_HEIGHT = 100
NUM_REELS = 3
REEL_SPACING = 50

# Game Phases
class GamePhase(str, Enum):
    MENU = "MENU"
    IDLE = "IDLE"
    SPINNING = "SPINNING"
    RESULT_DISPLAY = "RESULT_DISPLAY"

class GameMode(str, Enum):
    CASUAL = "CASUAL"      # Score-only, no betting
    HARDCORE = "HARDCORE"  # Betting with credits

class ReelState(str, Enum):
    SPINNING = "SPINNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"

# Dataclasses
@dataclass
class Reel:
    """Single slot machine reel"""
    symbols: List[str] = field(default_factory=lambda:
        ['seven', 'bar', 'cherry', 'lemon', 'orange', 'watermelon'])
    current_offset: float = 0.0
    state: ReelState = ReelState.STOPPED
    final_symbol: str = 'seven'
    stop_time_ms: int = 0

    def reset(self):
        """Reset reel to initial state"""
        self.current_offset = 0.0
        self.state = ReelState.STOPPED

@dataclass
class SlotMachineState:
    """Main game state"""
    mode: Optional[GameMode] = None
    phase: GamePhase = GamePhase.MENU
    score: int = 0                # For casual mode
    credits: int = 1000           # For hardcore mode
    bet_amount: int = 10          # For hardcore mode
    reels: List[Reel] = field(default_factory=lambda: [Reel(), Reel(), Reel()])
    spin_start_ms: int = 0
    result_message: str = "Pull the lever!"
    total_spins: int = 0
    jackpots: int = 0
    input_cooldown_until_ms: int = 0
    result_display_until_ms: int = 0
    game_over: bool = False

    # Bet adjustment tracking (for accelerating key hold)
    bet_key_hold_start_ms: int = 0
    bet_last_update_ms: int = 0

    # Hand tracking state
    prev_fist_y: Optional[float] = None
    fist_motion_active: bool = False
    special_mode_active: bool = False


class BlinkDetector:
    """Detects eye blinks using dlib facial landmarks"""

    def __init__(self):
        try:
            import dlib
            self.detector = dlib.get_frontal_face_detector()
            model_path = os.path.join(
                os.path.dirname(__file__), '..', 'assets', 'models',
                'shape_predictor_68_face_landmarks.dat'
            )
            if not os.path.exists(model_path):
                print(f"Warning: dlib model not found at {model_path}")
                print("Blink detection will be disabled. Download from:")
                print("http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2")
                self.predictor = None
                self.enabled = False
            else:
                self.predictor = dlib.shape_predictor(model_path)
                self.enabled = True

            self.blink_threshold = 0.25
            self.consecutive_frames = 0
            self.frames_required = 2
            self.last_ear = 1.0
        except ImportError:
            print("Warning: dlib not installed. Blink detection disabled.")
            print("Install with: pip install dlib")
            self.enabled = False
            self.detector = None
            self.predictor = None
            self.last_ear = 1.0

    def eye_aspect_ratio(self, eye_points) -> float:
        """Calculate Eye Aspect Ratio (EAR)"""
        A = np.linalg.norm(eye_points[1] - eye_points[5])
        B = np.linalg.norm(eye_points[2] - eye_points[4])
        C = np.linalg.norm(eye_points[0] - eye_points[3])
        if C == 0:
            return 1.0
        return (A + B) / (2.0 * C)

    def detect_blink(self, frame) -> bool:
        """Returns True if blink detected"""
        if not self.enabled or self.predictor is None:
            return False

        try:
            import dlib
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.detector(gray, 0)

            if len(faces) == 0:
                self.consecutive_frames = 0
                return False

            for face in faces:
                landmarks = self.predictor(gray, face)

                # Extract eye landmarks (36-41: left, 42-47: right)
                left_eye = np.array([(landmarks.part(i).x, landmarks.part(i).y)
                                     for i in range(36, 42)])
                right_eye = np.array([(landmarks.part(i).x, landmarks.part(i).y)
                                      for i in range(42, 48)])

                left_ear = self.eye_aspect_ratio(left_eye)
                right_ear = self.eye_aspect_ratio(right_eye)
                avg_ear = (left_ear + right_ear) / 2.0

                self.last_ear = avg_ear

                if avg_ear < self.blink_threshold:
                    self.consecutive_frames += 1
                    if self.consecutive_frames >= self.frames_required:
                        self.consecutive_frames = 0
                        return True
                else:
                    self.consecutive_frames = 0

        except Exception as e:
            print(f"Blink detection error: {e}")

        return False


class FistMotionDetector:
    """Detects closed fist and downward motion using MediaPipe"""

    def __init__(self):
        try:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5
            )
            self.enabled = True
        except ImportError:
            print("Warning: mediapipe not found. Fist detection disabled.")
            self.enabled = False
            self.hands = None

        self.prev_fist_y_by_hand: Dict[str, float] = {}
        self.prev_fist_pos_by_hand: Dict[str, Tuple[float, float, float]] = {}
        self.downward_streak_by_hand: Dict[str, int] = {}
        self.motion_threshold = 0.012
        self.pull_consecutive_frames = 2
        self.pull_cooldown_ms = 320
        self.fist_detected_current_frame = False
        self.last_delta_y = 0.0
        self.current_y = 0.0
        self.active_fists = 0
        self.last_pull_ms_by_hand: Dict[str, int] = {}

        # Alternating dance combo detection (both fists, forward/backward).
        # Use Y axis for combo rhythm because webcam Z is often too flat/noisy.
        self.dance_axis = "y"
        self.prev_pair_axis: Optional[float] = None
        self.dance_motion_threshold = 0.008
        self.last_combo_ms = 0
        self.combo_steps = 0
        self.combo_timeout_ms = 1500
        self.combo_required_steps = 1
        self.combo_expected_direction = "forward"
        self.last_dual_fists_ms = 0
        self.dual_fist_grace_ms = 300
        self.last_detected_pull_hand = ""
        self.last_dance_direction = "-"
        self.last_dance_delta = 0.0

    def is_fist_closed(self, hand_landmarks) -> bool:
        """Detect if hand is in closed fist position"""
        landmarks = hand_landmarks.landmark

        # Fingertips (excluding thumb): 8, 12, 16, 20
        fingertip_ids = [8, 12, 16, 20]

        # Check if all fingertips are below their base (curled in)
        fingers_curled = 0
        for tip_id in fingertip_ids:
            base_id = tip_id - 2  # Base of each finger
            if landmarks[tip_id].y > landmarks[base_id].y:
                fingers_curled += 1

        # Fist if 3+ fingers are curled
        return fingers_curled >= 3

    def detect_pull_motion(self, frame, now_ms: int) -> Tuple[bool, bool, bool]:
        """
        Detect downward fist motion (lever pull).

        Returns:
            (pull_detected, dual_fists_active, dance_combo_triggered)
        """
        if not self.enabled or self.hands is None:
            return (False, False, False)

        self.fist_detected_current_frame = False
        self.active_fists = 0
        pull_detected = False
        dance_combo_triggered = False
        pulled_hands: List[Tuple[str, float]] = []

        try:
            imgRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(imgRGB)

            if not results.multi_hand_landmarks:
                self.prev_fist_y_by_hand.clear()
                self.prev_fist_pos_by_hand.clear()
                self.downward_streak_by_hand.clear()
                return (False, False, False)

            active_ids: Set[str] = set()
            fist_wrist_axis_by_hand: Dict[str, float] = {}
            for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                hand_id = f"idx_{idx}"
                if results.multi_handedness and idx < len(results.multi_handedness):
                    hand_info = results.multi_handedness[idx].classification[0]
                    hand_id = hand_info.label.lower()

                # Check if fist is closed
                if not self.is_fist_closed(hand_landmarks):
                    self.prev_fist_y_by_hand.pop(hand_id, None)
                    self.prev_fist_pos_by_hand.pop(hand_id, None)
                    self.downward_streak_by_hand.pop(hand_id, None)
                    continue

                active_ids.add(hand_id)
                self.fist_detected_current_frame = True
                self.active_fists += 1

                # Get current wrist position (landmark 0)
                current_x = hand_landmarks.landmark[0].x
                current_y = hand_landmarks.landmark[0].y
                wrist_z = hand_landmarks.landmark[0].z
                dance_value = current_y if self.dance_axis == "y" else wrist_z
                fist_wrist_axis_by_hand[hand_id] = dance_value
                self.current_y = current_y

                # Lever pull: strictly downward motion with axis dominance.
                prev_pos = self.prev_fist_pos_by_hand.get(hand_id)
                if prev_pos is not None:
                    prev_x, prev_y, prev_z = prev_pos
                    delta_y = current_y - prev_y
                    delta_x = abs(current_x - prev_x)
                    delta_z = abs(wrist_z - prev_z)
                    self.last_delta_y = delta_y

                    down_dominant = (
                        delta_y > self.motion_threshold
                        and delta_y > (delta_x * 1.25)
                        and delta_y > (delta_z * 1.25)
                    )

                    if down_dominant:
                        next_streak = self.downward_streak_by_hand.get(hand_id, 0) + 1
                        self.downward_streak_by_hand[hand_id] = next_streak
                    else:
                        self.downward_streak_by_hand[hand_id] = 0

                    if self.downward_streak_by_hand.get(hand_id, 0) >= self.pull_consecutive_frames:
                        last_ms = self.last_pull_ms_by_hand.get(hand_id, -999999)
                        if now_ms - last_ms >= self.pull_cooldown_ms:
                            print(
                                f"PULL DETECTED ({hand_id})! "
                                f"Delta: {delta_y:.3f} > Threshold: {self.motion_threshold}"
                            )
                            pulled_hands.append((hand_id, delta_y))
                            self.last_pull_ms_by_hand[hand_id] = now_ms
                            self.downward_streak_by_hand[hand_id] = 0
                            # Reset so same downward hold does not retrigger immediately.
                            self.prev_fist_y_by_hand.pop(hand_id, None)
                else:
                    self.last_delta_y = 0.0
                    self.prev_fist_y_by_hand[hand_id] = current_y
                    self.downward_streak_by_hand[hand_id] = 0

                if hand_id in self.prev_fist_y_by_hand:
                    self.prev_fist_y_by_hand[hand_id] = current_y
                self.prev_fist_pos_by_hand[hand_id] = (current_x, current_y, wrist_z)

            # Drop stale tracked hands no longer active as fists.
            stale_ids = [hid for hid in self.prev_fist_y_by_hand if hid not in active_ids]
            for hid in stale_ids:
                self.prev_fist_y_by_hand.pop(hid, None)
                self.prev_fist_pos_by_hand.pop(hid, None)
                self.downward_streak_by_hand.pop(hid, None)

        except Exception as e:
            print(f"Fist detection error: {e}")

        dual_fists_active = self.active_fists >= 2

        # Dance combo is separate from lever pull:
        # require both fists and alternating forward/backward wrist-Z motion.
        pair_axis: Optional[float] = None
        if "left" in fist_wrist_axis_by_hand and "right" in fist_wrist_axis_by_hand:
            pair_axis = (fist_wrist_axis_by_hand["left"] + fist_wrist_axis_by_hand["right"]) / 2.0
        elif len(fist_wrist_axis_by_hand) >= 2:
            pair_axis = float(np.mean(list(fist_wrist_axis_by_hand.values())[:2]))

        if dual_fists_active and pair_axis is not None:
            self.last_dual_fists_ms = now_ms
            if self.prev_pair_axis is not None:
                delta_axis = pair_axis - self.prev_pair_axis
                self.last_dance_delta = delta_axis
                detected_direction: Optional[str] = None
                if delta_axis <= -self.dance_motion_threshold:
                    detected_direction = "forward"
                elif delta_axis >= self.dance_motion_threshold:
                    detected_direction = "backward"

                if detected_direction is not None:
                    self.last_dance_direction = detected_direction
                    if now_ms - self.last_combo_ms > self.combo_timeout_ms:
                        self.combo_steps = 0
                        self.combo_expected_direction = "forward"

                    if detected_direction == self.combo_expected_direction:
                        self.combo_steps += 1
                    else:
                        # Restart sequence from this motion direction.
                        self.combo_steps = 1

                    self.combo_expected_direction = (
                        "backward" if detected_direction == "forward" else "forward"
                    )
                    self.last_combo_ms = now_ms

                    if self.combo_steps >= self.combo_required_steps:
                        dance_combo_triggered = True
                        self.combo_steps = 0
                        self.combo_expected_direction = "forward"
                        self.last_dance_direction = "triggered"
            self.prev_pair_axis = pair_axis
        else:
            if now_ms - self.last_dual_fists_ms > self.dual_fist_grace_ms:
                self.prev_pair_axis = None
                self.combo_steps = 0
                self.combo_expected_direction = "forward"
                self.last_dance_direction = "-"
                self.last_dance_delta = 0.0

        if pulled_hands:
            # Use the strongest downward pull if both happen in same frame.
            pull_detected = True
            pulled_hands.sort(key=lambda item: item[1], reverse=True)
            pulled_hand = pulled_hands[0][0]
            self.last_detected_pull_hand = pulled_hand
            self.last_delta_y = pulled_hands[0][1]

        return (pull_detected, dual_fists_active, dance_combo_triggered)


def generate_symbol_images() -> Dict[str, pygame.Surface]:
    """Generate realistic slot symbols with 3D effects"""
    symbols = {}

    # Seven (red with gradient and shine)
    seven = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    # Shadow
    shadow_font = pygame.font.SysFont('georgia', 70, bold=True)
    shadow = shadow_font.render('7', True, (60, 0, 0))
    seven.blit(shadow, (27, 7))
    # Main text with gradient effect
    font = pygame.font.SysFont('georgia', 70, bold=True)
    text = font.render('7', True, (255, 50, 50))
    seven.blit(text, (25, 5))
    # Highlight
    highlight = font.render('7', True, (255, 150, 150))
    highlight.set_alpha(120)
    seven.blit(highlight, (23, 3))
    # Glow
    glow_surf = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    pygame.draw.circle(glow_surf, (255, 0, 0, 60), (SYMBOL_HEIGHT // 2, SYMBOL_HEIGHT // 2), 45)
    seven.blit(glow_surf, (0, 0))
    symbols['seven'] = seven

    # BAR (chrome/gold with 3D effect)
    bar = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    # Outer bar (shadow)
    pygame.draw.rect(bar, (100, 80, 20), (13, 42, 74, 22), border_radius=4)
    # Main bar with gradient
    pygame.draw.rect(bar, (255, 215, 0), (15, 40, 70, 20), border_radius=4)
    pygame.draw.rect(bar, (255, 235, 100), (15, 40, 70, 8), border_radius=4)
    # Shine line
    pygame.draw.line(bar, (255, 255, 200), (20, 42), (80, 42), 2)
    # Text
    font = pygame.font.SysFont('impact', 16, bold=True)
    text = font.render('BAR', True, (40, 30, 0))
    bar.blit(text, (32, 46))
    symbols['bar'] = bar

    # Cherry (3D with highlights)
    cherry = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    # Shadow
    pygame.draw.circle(cherry, (80, 10, 20), (52, 57), 26)
    # Main cherry
    pygame.draw.circle(cherry, (220, 20, 60), (50, 55), 26)
    # Darker half
    pygame.draw.arc(cherry, (160, 10, 40), (24, 29, 52, 52), 0.5, 3.64, 26)
    # Shine
    pygame.draw.circle(cherry, (255, 100, 120), (42, 47), 8)
    pygame.draw.circle(cherry, (255, 180, 190), (40, 45), 4)
    # Stem
    pygame.draw.line(cherry, (34, 139, 34), (50, 29), (50, 35), 4)
    pygame.draw.circle(cherry, (34, 139, 34), (50, 29), 3)
    symbols['cherry'] = cherry

    # Lemon (3D)
    lemon = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    # Shadow
    pygame.draw.ellipse(lemon, (100, 100, 0), (23, 37, 54, 32))
    # Main lemon
    pygame.draw.ellipse(lemon, (255, 255, 0), (25, 35, 50, 30))
    pygame.draw.ellipse(lemon, (255, 255, 150), (25, 35, 50, 15))
    # Highlight
    pygame.draw.ellipse(lemon, (255, 255, 200), (30, 38, 20, 10))
    # Outline
    pygame.draw.ellipse(lemon, (200, 200, 0), (25, 35, 50, 30), 2)
    symbols['lemon'] = lemon

    # Orange (3D with texture)
    orange = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    # Shadow
    pygame.draw.circle(orange, (120, 70, 0), (52, 52), 29)
    # Main orange
    pygame.draw.circle(orange, (255, 140, 0), (50, 50), 28)
    # Darker arc
    pygame.draw.arc(orange, (200, 100, 0), (22, 22, 56, 56), 0.5, 3.64, 28)
    # Texture dots
    for dx, dy in [(-8, -5), (0, -8), (8, -5), (-6, 3), (6, 3)]:
        pygame.draw.circle(orange, (220, 110, 0), (50 + dx, 50 + dy), 2)
    # Highlight
    pygame.draw.circle(orange, (255, 180, 80), (42, 42), 10)
    pygame.draw.circle(orange, (255, 220, 150), (40, 40), 5)
    symbols['orange'] = orange

    # Watermelon (3D slice)
    watermelon = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    # Shadow
    pygame.draw.circle(watermelon, (20, 80, 20), (52, 52), 31)
    # Green rind
    pygame.draw.circle(watermelon, (34, 139, 34), (50, 50), 30)
    # Light green layer
    pygame.draw.circle(watermelon, (144, 238, 144), (50, 50), 26)
    # Red center
    pygame.draw.circle(watermelon, (255, 69, 69), (50, 50), 23)
    # Highlight
    pygame.draw.circle(watermelon, (255, 120, 120), (42, 42), 12)
    pygame.draw.circle(watermelon, (255, 180, 180), (40, 40), 6)
    # Seeds
    for x, y in [(42, 45), (58, 45), (50, 55), (46, 52), (54, 52)]:
        pygame.draw.ellipse(watermelon, (0, 0, 0), (x-2, y-3, 4, 6))
    symbols['watermelon'] = watermelon

    return symbols


def draw_gradient_background(surface: pygame.Surface):
    """Draw 1950s Vegas gradient background"""
    for y in range(WINDOW_HEIGHT):
        blend = y / float(WINDOW_HEIGHT)
        color = (
            int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * blend),
            int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * blend),
            int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * blend),
        )
        pygame.draw.line(surface, color, (0, y), (WINDOW_WIDTH, y))


def draw_scanlines(surface: pygame.Surface):
    """Draw CRT-style scanline overlay"""
    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    for y in range(0, WINDOW_HEIGHT, 4):
        pygame.draw.line(overlay, (0, 0, 0, 30), (0, y), (WINDOW_WIDTH, y))
    surface.blit(overlay, (0, 0))


def draw_slot_machine_cabinet(surface: pygame.Surface, x: int, y: int, width: int, height: int):
    """Draw realistic slot machine cabinet with wood paneling and chrome"""
    # Main cabinet body (wood grain effect)
    cabinet = pygame.Rect(x - 30, y - 30, width + 60, height + 80)

    # Wood panels
    for i in range(0, cabinet.height, 3):
        shade = 45 + (i % 12)
        pygame.draw.line(surface, (shade, shade - 10, shade - 15),
                        (cabinet.x, cabinet.y + i), (cabinet.x + cabinet.width, cabinet.y + i))

    # Chrome top border
    pygame.draw.rect(surface, (180, 180, 180), (cabinet.x, cabinet.y, cabinet.width, 15))
    pygame.draw.rect(surface, (220, 220, 220), (cabinet.x, cabinet.y, cabinet.width, 6))
    pygame.draw.rect(surface, (140, 140, 140), (cabinet.x, cabinet.y + 8, cabinet.width, 3))

    # Chrome side panels
    pygame.draw.rect(surface, (160, 160, 160), (cabinet.x, cabinet.y, 15, cabinet.height))
    pygame.draw.rect(surface, (200, 200, 200), (cabinet.x, cabinet.y, 6, cabinet.height))
    pygame.draw.rect(surface, (160, 160, 160), (cabinet.x + cabinet.width - 15, cabinet.y, 15, cabinet.height))

    # Decorative rivets
    rivet_color = (120, 120, 120)
    for rx in range(cabinet.x + 40, cabinet.x + cabinet.width - 40, 80):
        pygame.draw.circle(surface, rivet_color, (rx, cabinet.y + 10), 4)
        pygame.draw.circle(surface, (180, 180, 180), (rx, cabinet.y + 10), 3)
        pygame.draw.circle(surface, rivet_color, (rx, cabinet.y + cabinet.height - 10), 4)
        pygame.draw.circle(surface, (180, 180, 180), (rx, cabinet.y + cabinet.height - 10), 3)


def draw_lever(surface: pygame.Surface, x: int, y: int, pull_progress: float):
    """Draw animated slot machine lever"""
    # Lever base
    base_rect = pygame.Rect(x, y, 25, 40)
    pygame.draw.rect(surface, (80, 80, 80), base_rect, border_radius=8)
    pygame.draw.rect(surface, (120, 120, 120), base_rect, border_radius=8, width=2)

    # Lever arm (rotates based on pull_progress)
    arm_length = 120
    angle = -0.3 + (pull_progress * 0.8)  # Rotates as you pull
    end_x = x + 12 + int(arm_length * 0.3 * pull_progress)
    end_y = y + 20 + int(arm_length * (1 - 0.6 * pull_progress))

    # Arm shadow
    pygame.draw.line(surface, (40, 40, 40), (x + 14, y + 22), (end_x + 2, end_y + 2), 12)
    # Main arm
    pygame.draw.line(surface, (180, 180, 180), (x + 12, y + 20), (end_x, end_y), 10)
    # Highlight
    pygame.draw.line(surface, (220, 220, 220), (x + 12, y + 20), (end_x, end_y), 6)

    # Red ball handle
    ball_x, ball_y = end_x, end_y
    pygame.draw.circle(surface, (100, 0, 0), (ball_x + 2, ball_y + 2), 18)  # Shadow
    pygame.draw.circle(surface, (200, 0, 0), (ball_x, ball_y), 18)
    pygame.draw.circle(surface, (255, 50, 50), (ball_x - 4, ball_y - 4), 10)


def draw_reel(surface: pygame.Surface, reel: Reel, x: int, y: int,
              symbol_images: Dict[str, pygame.Surface]):
    """Draw a single reel with realistic effects"""
    # Inner shadow
    shadow_rect = pygame.Rect(x - 3, y - 3, REEL_WIDTH + 6, REEL_HEIGHT + 6)
    pygame.draw.rect(surface, (20, 20, 20), shadow_rect, border_radius=8)

    # Reel background (darker)
    reel_rect = pygame.Rect(x, y, REEL_WIDTH, REEL_HEIGHT)
    pygame.draw.rect(surface, (15, 15, 20), reel_rect, border_radius=6)

    # Create clipping region
    clip_rect = surface.get_clip()
    surface.set_clip(reel_rect)

    # Draw symbols
    if reel.state == ReelState.SPINNING:
        # During spinning, cycle through ALL symbols based on scroll position
        # Calculate which symbols are visible based on current_offset
        offset_index = int(reel.current_offset / SYMBOL_HEIGHT) % len(reel.symbols)
        # Draw 4 symbols to ensure smooth scrolling (need extra for top/bottom)
        symbols_to_draw = [
            reel.symbols[(offset_index) % len(reel.symbols)],
            reel.symbols[(offset_index + 1) % len(reel.symbols)],
            reel.symbols[(offset_index + 2) % len(reel.symbols)],
            reel.symbols[(offset_index + 3) % len(reel.symbols)]
        ]

        for i, symbol in enumerate(symbols_to_draw):
            img = symbol_images[symbol]
            # Use modulo of current_offset for smooth continuous scrolling
            offset_within_symbol = reel.current_offset % SYMBOL_HEIGHT
            pos_y = y + (i * SYMBOL_HEIGHT) - offset_within_symbol
            pos_x = x + (REEL_WIDTH - SYMBOL_HEIGHT) // 2

            # Apply motion blur during spinning
            blurred = img.copy()
            blurred.set_alpha(150)
            surface.blit(blurred, (pos_x, pos_y))
    else:
        # During stopping/stopped, show final result
        final_idx = reel.symbols.index(reel.final_symbol)
        symbols_to_draw = [
            reel.symbols[(final_idx - 1) % len(reel.symbols)],
            reel.final_symbol,
            reel.symbols[(final_idx + 1) % len(reel.symbols)]
        ]

        for i, symbol in enumerate(symbols_to_draw):
            img = symbol_images[symbol]
            pos_y = y + (i * SYMBOL_HEIGHT) - reel.current_offset
            pos_x = x + (REEL_WIDTH - SYMBOL_HEIGHT) // 2
            surface.blit(img, (pos_x, pos_y))

    surface.set_clip(clip_rect)

    # Chrome border around reel
    pygame.draw.rect(surface, (100, 100, 100), reel_rect, width=3, border_radius=6)
    pygame.draw.rect(surface, (180, 180, 180), reel_rect, width=2, border_radius=6)

    # Glass reflection effect
    glass_overlay = pygame.Surface((REEL_WIDTH, REEL_HEIGHT), pygame.SRCALPHA)
    # Diagonal shine
    for i in range(0, REEL_WIDTH + REEL_HEIGHT, 8):
        alpha = 15
        pygame.draw.line(glass_overlay, (255, 255, 255, alpha),
                        (i, 0), (i - REEL_HEIGHT, REEL_HEIGHT), 3)
    surface.blit(glass_overlay, (x, y))


def draw_neon_text(surface: pygame.Surface, text: str, font: pygame.font.Font,
                   color: Tuple[int, int, int], pos: Tuple[int, int],
                   glow: bool = True):
    """Draw text with neon glow effect"""
    if glow:
        # Draw glow
        for offset in [(2, 2), (-2, -2), (2, -2), (-2, 2)]:
            glow_surf = font.render(text, True, (color[0] // 3, color[1] // 3, color[2] // 3))
            glow_surf.set_alpha(100)
            surface.blit(glow_surf, (pos[0] + offset[0], pos[1] + offset[1]))

    # Draw main text
    text_surf = font.render(text, True, color)
    surface.blit(text_surf, pos)


def draw_ui(surface: pygame.Surface, state: SlotMachineState):
    """Draw UI elements (score, title, messages)"""
    # Title
    title_font = pygame.font.SysFont('georgia', 56, bold=True)
    draw_neon_text(surface, 'SLOT MACHINE', title_font, NEON_PINK,
                   (WINDOW_WIDTH // 2 - 280, 30))

    subtitle_font = pygame.font.SysFont('georgia', 24, bold=True)
    draw_neon_text(surface, '1950s VEGAS', subtitle_font, NEON_CYAN,
                   (WINDOW_WIDTH // 2 - 90, 90), glow=False)

    # Stats panel
    stats_font = pygame.font.SysFont('arial', 24, bold=True)
    stats_y = 140

    if state.mode == GameMode.CASUAL:
        # Casual mode: Show score
        score_text = f"SCORE: {state.score}"
        draw_neon_text(surface, score_text, stats_font, NEON_GOLD,
                       (50, stats_y), glow=False)

        # Spins
        spins_text = f"SPINS: {state.total_spins}"
        draw_neon_text(surface, spins_text, stats_font, TEXT_CREAM,
                       (300, stats_y), glow=False)

        # Jackpots
        jackpot_text = f"JACKPOTS: {state.jackpots}"
        draw_neon_text(surface, jackpot_text, stats_font, NEON_PINK,
                       (550, stats_y), glow=False)

        # Mode indicator
        mode_text = "MODE: CASUAL"
        draw_neon_text(surface, mode_text, stats_font, NEON_CYAN,
                       (700, stats_y), glow=False)

    else:  # GameMode.HARDCORE
        # Hardcore mode: Show credits and bet
        credits_text = f"CREDITS: {state.credits}"
        credits_color = NEON_GOLD if state.credits >= 500 else (255, 100, 100) if state.credits < 100 else TEXT_CREAM
        draw_neon_text(surface, credits_text, stats_font, credits_color,
                       (50, stats_y), glow=False)

        # Bet amount
        bet_text = f"BET: {state.bet_amount} (↑↓)"
        draw_neon_text(surface, bet_text, stats_font, NEON_CYAN,
                       (300, stats_y), glow=False)

        # Spins
        spins_text = f"SPINS: {state.total_spins}"
        draw_neon_text(surface, spins_text, stats_font, TEXT_CREAM,
                       (550, stats_y), glow=False)

        # Jackpots
        jackpot_text = f"JACKPOTS: {state.jackpots}"
        draw_neon_text(surface, jackpot_text, stats_font, NEON_PINK,
                       (700, stats_y), glow=False)

    # Result message (bottom right, to the right of payout box)
    msg_font = pygame.font.SysFont('georgia', 32, bold=True)
    if "GAME OVER" in state.result_message:
        msg_color = (255, 50, 50)  # Red for game over
    elif "JACKPOT" in state.result_message:
        msg_color = NEON_GOLD
    else:
        msg_color = TEXT_CREAM
    msg_surface = msg_font.render(state.result_message, True, msg_color)
    # Position to the right of payout box (payout box ends at x=390)
    msg_rect = msg_surface.get_rect(center=(620, WINDOW_HEIGHT - 90))
    surface.blit(msg_surface, msg_rect)

    # Mode indicator in top right corner
    mode_font = pygame.font.SysFont('arial', 20, bold=True)
    if state.mode == GameMode.CASUAL:
        mode_display = "CASUAL MODE"
        mode_color = NEON_CYAN
    else:
        mode_display = "HARDCORE MODE"
        mode_color = NEON_PINK

    # Draw mode text in top right with background
    mode_surface = mode_font.render(mode_display, True, mode_color)
    mode_width = mode_surface.get_width()
    mode_x = WINDOW_WIDTH - mode_width - 20
    mode_y = 20

    # Background box
    bg_rect = pygame.Rect(mode_x - 10, mode_y - 5, mode_width + 20, 30)
    pygame.draw.rect(surface, (20, 10, 30), bg_rect, border_radius=8)
    pygame.draw.rect(surface, mode_color, bg_rect, width=2, border_radius=8)

    # Text
    surface.blit(mode_surface, (mode_x, mode_y))

    if state.special_mode_active:
        special_font = pygame.font.SysFont('arial', 19, bold=True)
        special_surface = special_font.render("SPECIAL MODE: MACARENA", True, NEON_GOLD)
        special_bg = pygame.Rect(mode_x - 90, mode_y + 34, special_surface.get_width() + 16, 30)
        pygame.draw.rect(surface, (30, 15, 10), special_bg, border_radius=8)
        pygame.draw.rect(surface, NEON_GOLD, special_bg, width=2, border_radius=8)
        surface.blit(special_surface, (special_bg.x + 8, special_bg.y + 5))


def draw_main_menu(surface: pygame.Surface) -> tuple:
    """Draw main menu for mode selection and return clickable boxes"""
    # Title
    title_font = pygame.font.SysFont('georgia', 72, bold=True)
    draw_neon_text(surface, 'SLOT MACHINE', title_font, NEON_PINK,
                   (WINDOW_WIDTH // 2 - 340, 80), glow=True)

    subtitle_font = pygame.font.SysFont('georgia', 32, bold=True)
    draw_neon_text(surface, '1950s VEGAS', subtitle_font, NEON_CYAN,
                   (WINDOW_WIDTH // 2 - 120, 170), glow=True)

    # Mode selection prompt
    prompt_font = pygame.font.SysFont('arial', 28, bold=True)
    prompt_text = "SELECT GAME MODE"
    draw_neon_text(surface, prompt_text, prompt_font, TEXT_CREAM,
                   (WINDOW_WIDTH // 2 - 160, 280), glow=False)

    # Casual Mode Box
    casual_box = pygame.Rect(150, 360, 280, 240)
    pygame.draw.rect(surface, (40, 20, 60), casual_box, border_radius=12)
    pygame.draw.rect(surface, NEON_CYAN, casual_box, width=4, border_radius=12)

    mode_font = pygame.font.SysFont('georgia', 36, bold=True)
    casual_title = mode_font.render('CASUAL', True, NEON_CYAN)
    surface.blit(casual_title, (210, 390))

    desc_font = pygame.font.SysFont('arial', 18)
    casual_desc = [
        "• No betting",
        "• Accumulate score",
        "• Play forever",
        "• Relaxed fun"
    ]
    for i, line in enumerate(casual_desc):
        text = desc_font.render(line, True, TEXT_CREAM)
        surface.blit(text, (170, 450 + i * 30))

    key_font = pygame.font.SysFont('arial', 24, bold=True)
    casual_key = key_font.render('Press C or Click', True, NEON_CYAN)
    surface.blit(casual_key, (195, 560))

    # Hardcore Mode Box
    hardcore_box = pygame.Rect(470, 360, 280, 240)
    pygame.draw.rect(surface, (40, 20, 60), hardcore_box, border_radius=12)
    pygame.draw.rect(surface, NEON_PINK, hardcore_box, width=4, border_radius=12)

    hardcore_title = mode_font.render('HARDCORE', True, NEON_PINK)
    surface.blit(hardcore_title, (505, 390))

    hardcore_desc = [
        "• Bet credits",
        "• Start with 1000",
        "• Risk vs Reward",
        "• Vegas thrill"
    ]
    for i, line in enumerate(hardcore_desc):
        text = desc_font.render(line, True, TEXT_CREAM)
        surface.blit(text, (490, 450 + i * 30))

    hardcore_key = key_font.render('Press H or Click', True, NEON_PINK)
    surface.blit(hardcore_key, (515, 560))

    # Bottom instruction
    bottom_font = pygame.font.SysFont('arial', 18)
    bottom_text = "Click on mode boxes or use keyboard (C/H)"
    text_surface = bottom_font.render(bottom_text, True, (150, 150, 150))
    surface.blit(text_surface, (WINDOW_WIDTH // 2 - 200, 640))

    # Return clickable boxes for mouse detection
    return casual_box, hardcore_box


def can_trigger_spin(state: SlotMachineState, now_ms: int) -> bool:
    """Check if spin can be triggered"""
    if state.phase != GamePhase.IDLE or now_ms < state.input_cooldown_until_ms or state.game_over:
        return False

    # In hardcore mode, check if player has any credits
    if state.mode == GameMode.HARDCORE:
        return state.credits > 0

    # In casual mode, can always spin
    return True


def start_spin(state: SlotMachineState, now_ms: int):
    """Start spinning the reels"""
    # In hardcore mode, auto-adjust bet and deduct
    if state.mode == GameMode.HARDCORE:
        # Auto-adjust bet if it's higher than remaining credits
        if state.bet_amount > state.credits:
            state.bet_amount = max(10, state.credits)
        state.credits -= state.bet_amount

    state.phase = GamePhase.SPINNING
    state.spin_start_ms = now_ms
    state.total_spins += 1
    state.result_message = "SPINNING..."

    # Randomize final symbols and set stop times
    for i, reel in enumerate(state.reels):
        reel.final_symbol = random.choice(reel.symbols)
        reel.state = ReelState.SPINNING
        reel.stop_time_ms = now_ms + 1200 + (i * 400)  # Staggered: 1.2s, 1.6s, 2.0s
        reel.current_offset = 0.0


def update_game(state: SlotMachineState, now_ms: int, audio_effects: Optional[GameAudioEffects] = None):
    """Update game logic each frame"""
    if state.phase == GamePhase.SPINNING:
        # Update each reel
        for reel in state.reels:
            if reel.state == ReelState.SPINNING:
                # Scroll animation - let it accumulate continuously
                reel.current_offset += 30

                # Check if should stop
                if now_ms >= reel.stop_time_ms:
                    reel.state = ReelState.STOPPING
                    # Reset offset to a small value that will ease to 0
                    # This creates a smooth deceleration effect
                    reel.current_offset = 80.0

            elif reel.state == ReelState.STOPPING:
                # Ease to final position (offset approaches 0)
                reel.current_offset *= 0.85
                if abs(reel.current_offset) < 1:
                    reel.current_offset = 0
                    reel.state = ReelState.STOPPED

        # Check if all stopped
        if all(r.state == ReelState.STOPPED for r in state.reels):
            check_win(state, now_ms, audio_effects=audio_effects)

    elif state.phase == GamePhase.RESULT_DISPLAY:
        # Wait 2 seconds then return to idle
        if now_ms >= state.result_display_until_ms:
            state.phase = GamePhase.IDLE
            state.result_message = "Pull the lever!"


def check_win(state: SlotMachineState, now_ms: int, audio_effects: Optional[GameAudioEffects] = None):
    """Check for winning combinations and award points/credits"""
    symbols = [reel.final_symbol for reel in state.reels]
    is_win_result = False

    if state.mode == GameMode.CASUAL:
        # Casual mode: Fixed score points
        # 3 matching sevens (JACKPOT)
        if symbols[0] == symbols[1] == symbols[2] == 'seven':
            state.score += 500
            state.jackpots += 1
            state.result_message = "🎰 JACKPOT! 777! +500 🎰"
            is_win_result = True

        # 3 matching BARs
        elif symbols[0] == symbols[1] == symbols[2] == 'bar':
            state.score += 100
            state.result_message = "⭐ THREE BARS! +100 ⭐"
            is_win_result = True

        # 3 matching fruits
        elif symbols[0] == symbols[1] == symbols[2]:
            state.score += 50
            state.result_message = f"✨ THREE {symbols[0].upper()}S! +50 ✨"
            is_win_result = True

        # 2 matching
        elif (symbols[0] == symbols[1] or
              symbols[1] == symbols[2] or
              symbols[0] == symbols[2]):
            state.score += 10
            state.result_message = "Two Match! +10"
            is_win_result = True

        # No match
        else:
            state.result_message = "No match. Try again!"

    else:  # GameMode.HARDCORE
        # Hardcore mode: Bet multipliers with credits
        winnings = 0

        # 3 matching sevens (JACKPOT)
        if symbols[0] == symbols[1] == symbols[2] == 'seven':
            winnings = state.bet_amount * 50
            state.credits += winnings
            state.jackpots += 1
            state.result_message = f"🎰 JACKPOT! 777! +{winnings} 🎰"
            is_win_result = True

        # 3 matching BARs
        elif symbols[0] == symbols[1] == symbols[2] == 'bar':
            winnings = state.bet_amount * 10
            state.credits += winnings
            state.result_message = f"⭐ THREE BARS! +{winnings} ⭐"
            is_win_result = True

        # 3 matching fruits
        elif symbols[0] == symbols[1] == symbols[2]:
            winnings = state.bet_amount * 5
            state.credits += winnings
            state.result_message = f"✨ THREE {symbols[0].upper()}S! +{winnings} ✨"
            is_win_result = True

        # 2 matching (return bet)
        elif (symbols[0] == symbols[1] or
              symbols[1] == symbols[2] or
              symbols[0] == symbols[2]):
            winnings = state.bet_amount
            state.credits += winnings
            state.result_message = f"Two Match! Bet returned ({winnings})"
            is_win_result = True

        # No match (already lost bet)
        else:
            state.result_message = "No match. Try again!"

        # Check for game over in hardcore mode (only at 0 credits)
        if state.credits <= 0:
            state.game_over = True
            state.result_message = "💔 GAME OVER! Out of credits! 💔"

    if audio_effects is not None:
        if is_win_result:
            audio_effects.play_win()
        else:
            audio_effects.play_lose()

    state.phase = GamePhase.RESULT_DISPLAY
    state.result_display_until_ms = now_ms + 2000


def draw_payout_table(surface: pygame.Surface, state: SlotMachineState):
    """Draw payout table"""
    table_x = 30
    table_y = WINDOW_HEIGHT - 150  # Bottom left, 150px from bottom
    table_width = 360
    table_height = 120  # Shortened from 140
    font = pygame.font.SysFont('arial', 17, bold=True)

    # Title
    title_font = pygame.font.SysFont('arial', 20, bold=True)
    title = title_font.render('PAYOUTS', True, NEON_GOLD)
    surface.blit(title, (table_x + 20, table_y - 30))

    # Background panel
    pygame.draw.rect(surface, (30, 20, 35), (table_x, table_y, table_width, table_height), border_radius=8)
    pygame.draw.rect(surface, ACCENT, (table_x, table_y, table_width, table_height), 2, border_radius=8)

    # Payouts based on mode
    if state.mode == GameMode.CASUAL:
        payouts = [
            ("3 Sevens (777)", "+500", NEON_PINK),
            ("3 BARs", "+100", NEON_GOLD),
            ("3 Matching Fruits", "+50", TEXT_CREAM),
            ("2 Matching", "+10", TEXT_CREAM)
        ]
    else:  # GameMode.HARDCORE
        payouts = [
            ("3 Sevens (777)", "Bet × 50", NEON_PINK),
            ("3 BARs", "Bet × 10", NEON_GOLD),
            ("3 Matching Fruits", "Bet × 5", TEXT_CREAM),
            ("2 Matching", "Bet × 1", TEXT_CREAM)
        ]

    for i, (desc, payout_text, color) in enumerate(payouts):
        y = table_y + 12 + (i * 27)  # Compact spacing
        text = font.render(desc, True, color)
        surface.blit(text, (table_x + 15, y))
        points_text = font.render(payout_text, True, color)
        surface.blit(points_text, (table_x + 240, y))  # Adjusted for wider table


def render_game(surface: pygame.Surface, state: SlotMachineState,
                symbol_images: Dict[str, pygame.Surface]) -> Optional[tuple]:
    """Render the game and return menu boxes if in menu phase"""
    # Background
    draw_gradient_background(surface)

    # Show menu if in MENU phase
    if state.phase == GamePhase.MENU:
        return draw_main_menu(surface)

    # UI
    draw_ui(surface, state)

    # Calculate reel positions (centered)
    total_reel_width = (NUM_REELS * REEL_WIDTH) + ((NUM_REELS - 1) * REEL_SPACING)
    start_x = (WINDOW_WIDTH - total_reel_width) // 2
    reels_y = 200

    # Draw slot machine cabinet
    draw_slot_machine_cabinet(surface, start_x, reels_y, total_reel_width, REEL_HEIGHT)

    # Draw reels
    for i, reel in enumerate(state.reels):
        reel_x = start_x + (i * (REEL_WIDTH + REEL_SPACING))
        draw_reel(surface, reel, reel_x, reels_y, symbol_images)

    # Draw animated lever
    lever_pull = 0.0
    if state.phase == GamePhase.SPINNING:
        # Lever animates down during spin
        elapsed = pygame.time.get_ticks() - state.spin_start_ms
        if elapsed < 500:  # Pull animation lasts 0.5s
            lever_pull = min(1.0, elapsed / 500.0)
    draw_lever(surface, start_x + total_reel_width + 40, reels_y + 50, lever_pull)

    # Draw payout table
    draw_payout_table(surface, state)

    # Scanlines overlay
    draw_scanlines(surface)

    return None


def main():
    """Main game loop"""
    # Initialize pygame
    pygame.init()
    os.environ['SDL_VIDEO_WINDOW_POS'] = "700,100"
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption('Slot Machine 1950s Vegas')
    clock = pygame.time.Clock()
    audio_effects = GameAudioEffects()
    audio_effects.play_boot()
    special_song_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "assets",
            "audio_effects",
            "music",
            "trump_macarena.mp3",
        )
    )

    # Initialize CV
    cam = cv2.VideoCapture(0)
    fist_detector = FistMotionDetector()

    # Load assets
    symbol_images = generate_symbol_images()

    # Game state
    state = SlotMachineState()

    # Main loop
    running = True
    print("Slot Machine 1950s Vegas started!")
    print("Select game mode:")
    print("  - Press C for CASUAL mode (score-only, no betting)")
    print("  - Press H for HARDCORE mode (betting with credits)")
    print("  - ESC to quit")

    while running:
        now_ms = pygame.time.get_ticks()

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # Mode selection
                if state.phase == GamePhase.MENU:
                    if event.key == pygame.K_c:
                        # Select Casual mode
                        state.mode = GameMode.CASUAL
                        state.phase = GamePhase.IDLE
                        state.result_message = "Pull the lever!"
                        print("\nCasual mode selected!")
                        print("Controls:")
                        print("  - Pull fist down or press SPACEBAR to spin")
                        print("  - ESC to quit")
                    elif event.key == pygame.K_h:
                        # Select Hardcore mode
                        state.mode = GameMode.HARDCORE
                        state.phase = GamePhase.IDLE
                        state.result_message = "Pull the lever!"
                        print("\nHardcore mode selected!")
                        print("Starting credits: 1000")
                        print("Controls:")
                        print("  - Pull fist down or press SPACEBAR to spin")
                        print("  - UP/DOWN arrows to adjust bet amount")
                        print("  - ESC to quit")

                # Spacebar to spin (only when not in menu)
                if event.key == pygame.K_SPACE and state.phase != GamePhase.MENU:
                    if can_trigger_spin(state, now_ms):
                        start_spin(state, now_ms)
                        state.input_cooldown_until_ms = now_ms + 2000

            # Mouse click handling
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
                if state.phase == GamePhase.MENU and hasattr(state, 'menu_boxes') and state.menu_boxes:
                    mouse_pos = event.pos
                    casual_box, hardcore_box = state.menu_boxes

                    # Check if clicked on Casual box
                    if casual_box.collidepoint(mouse_pos):
                        state.mode = GameMode.CASUAL
                        state.phase = GamePhase.IDLE
                        state.result_message = "Pull the lever!"
                        print("\nCasual mode selected!")
                        print("Controls:")
                        print("  - Pull fist down or press SPACEBAR to spin")
                        print("  - ESC to quit")

                    # Check if clicked on Hardcore box
                    elif hardcore_box.collidepoint(mouse_pos):
                        state.mode = GameMode.HARDCORE
                        state.phase = GamePhase.IDLE
                        state.result_message = "Pull the lever!"
                        print("\nHardcore mode selected!")
                        print("Starting credits: 1000")
                        print("Controls:")
                        print("  - Pull fist down or press SPACEBAR to spin")
                        print("  - UP/DOWN arrows to adjust bet amount")
                        print("  - ESC to quit")

        # Handle continuous bet adjustment with acceleration (hardcore mode only)
        if state.mode == GameMode.HARDCORE and state.phase == GamePhase.IDLE:
            keys = pygame.key.get_pressed()
            up_held = keys[pygame.K_UP]
            down_held = keys[pygame.K_DOWN]

            if up_held or down_held:
                # Key is being held
                if state.bet_key_hold_start_ms == 0:
                    # Just started holding
                    state.bet_key_hold_start_ms = now_ms
                    state.bet_last_update_ms = now_ms

                # Calculate hold duration
                hold_duration_ms = now_ms - state.bet_key_hold_start_ms

                # Calculate update interval with acceleration
                # Start at 200ms, reduce to 50ms after 1 second
                if hold_duration_ms < 500:
                    update_interval = 200  # Slow at first
                elif hold_duration_ms < 1000:
                    update_interval = 100  # Medium speed
                else:
                    update_interval = 50   # Fast after 1 second

                # Calculate step size with acceleration
                # Start at 10, increase to 50 after 2 seconds
                if hold_duration_ms < 1000:
                    step_size = 10
                elif hold_duration_ms < 2000:
                    step_size = 25
                else:
                    step_size = 50

                # Check if enough time has passed for next update
                if now_ms - state.bet_last_update_ms >= update_interval:
                    state.bet_last_update_ms = now_ms

                    if up_held:
                        # Increase bet (no max limit)
                        state.bet_amount += step_size
                    elif down_held:
                        # Decrease bet (min: 10)
                        if state.bet_amount > 10:
                            state.bet_amount = max(state.bet_amount - step_size, 10)
            else:
                # No key held, reset tracking
                state.bet_key_hold_start_ms = 0
                state.bet_last_update_ms = 0

        # Process webcam frame
        success, frame = cam.read()
        if success:
            frame = cv2.flip(frame, 1)

            # Draw debug info on CV window
            if state.phase == GamePhase.MENU:
                # Menu mode
                cv2.putText(frame, "SELECT GAME MODE",
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(frame, "Press C = Casual | Press H = Hardcore",
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                # Game mode - check fist pull motion
                pull_detected, dual_fists_active, dance_combo_triggered = fist_detector.detect_pull_motion(frame, now_ms)

                if dance_combo_triggered and not state.special_mode_active:
                    if os.path.exists(special_song_path):
                        try:
                            pygame.mixer.music.load(special_song_path)
                            pygame.mixer.music.set_volume(0.85)
                            pygame.mixer.music.play()
                            state.special_mode_active = True
                            print("SPECIAL MODE ACTIVATED: alternating dual-fist dance combo -> Macarena track started.")
                        except pygame.error as err:
                            print(f"Warning: failed to start special music: {err}")
                    else:
                        print(f"Warning: special music file missing: {special_song_path}")

                # Hide special-mode badge once one-shot Macarena playback completes.
                if state.special_mode_active and not pygame.mixer.music.get_busy():
                    state.special_mode_active = False

                if pull_detected and can_trigger_spin(state, now_ms):
                    start_spin(state, now_ms)
                    state.input_cooldown_until_ms = now_ms + 2000

                # Show appropriate stats based on mode
                if state.mode == GameMode.CASUAL:
                    cv2.putText(frame, f"Score: {state.score} | Mode: CASUAL",
                               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    cv2.putText(frame, f"Credits: {state.credits} | Bet: {state.bet_amount}",
                               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                status_text = "READY" if can_trigger_spin(state, now_ms) else "COOLDOWN"
                if state.game_over:
                    status_text = "GAME OVER"
                cv2.putText(frame, f"Status: {status_text}",
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if status_text == "READY" else (100, 100, 255), 2)
                cv2.putText(frame, "Pull fist down to spin!",
                           (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame, "(Or press SPACEBAR)",
                           (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                cv2.putText(frame, f"Fists active: {fist_detector.active_fists}",
                           (10, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 240, 255), 1)
                cv2.putText(
                    frame,
                    f"Last pull hand: {fist_detector.last_detected_pull_hand or '-'}",
                    (10, 172),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (220, 220, 180),
                    1,
                )
                cv2.putText(
                    frame,
                    (
                        f"Dance combo: {fist_detector.combo_steps}/"
                        f"{fist_detector.combo_required_steps} "
                        f"last={fist_detector.last_dance_direction} "
                        f"next={fist_detector.combo_expected_direction} "
                        f"d{fist_detector.dance_axis}={fist_detector.last_dance_delta:.3f}"
                    ),
                    (10, 198),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 215, 0),
                    1,
                )
                if state.special_mode_active:
                    cv2.putText(frame, "SPECIAL MODE: MACARENA",
                               (10, 224), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 215, 255), 2)

            if fist_detector.fist_detected_current_frame:
                cv2.putText(frame, "FIST DETECTED!",
                           (10, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                # Show Y position and delta for debugging
                cv2.putText(frame, f"Y: {fist_detector.current_y:.3f}",
                           (10, 285), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
                cv2.putText(frame, f"Delta: {fist_detector.last_delta_y:.3f}",
                           (10, 312), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
                cv2.putText(frame, f"Need: {fist_detector.motion_threshold:.3f}",
                           (10, 339), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 100), 1)

            cv2.imshow("Slot Machine Controls", frame)
            cv2.waitKey(1)

        # Update game state
        update_game(state, now_ms, audio_effects=audio_effects)

        # Render and store menu boxes if in menu phase
        menu_boxes = render_game(screen, state, symbol_images)
        if menu_boxes:
            state.menu_boxes = menu_boxes
        pygame.display.flip()
        clock.tick(FPS)

    # Cleanup
    cam.release()
    cv2.destroyAllWindows()
    pygame.quit()

    # Show final stats
    if state.mode:
        print(f"\n{'='*50}")
        print(f"Game Over!")
        print(f"Mode: {state.mode.value}")
        if state.mode == GameMode.CASUAL:
            print(f"Final Score: {state.score}")
        else:
            print(f"Final Credits: {state.credits}")
        print(f"Total Spins: {state.total_spins}")
        print(f"Jackpots Won: {state.jackpots}")
        print(f"{'='*50}")


if __name__ == '__main__':
    main()
