import pygame
import cv2
import numpy as np
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional

'''
Slot Machine 1950s Vegas
Computer vision-controlled slot machine game with blink and fist motion detection
Created for UAIS SillyCon Valley Hackathon 2026
'''

# Global Constants
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
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
    IDLE = "IDLE"
    SPINNING = "SPINNING"
    RESULT_DISPLAY = "RESULT_DISPLAY"

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
    score: int = 0
    phase: GamePhase = GamePhase.IDLE
    reels: List[Reel] = field(default_factory=lambda: [Reel(), Reel(), Reel()])
    spin_start_ms: int = 0
    result_message: str = "Pull the lever!"
    total_spins: int = 0
    jackpots: int = 0
    input_cooldown_until_ms: int = 0
    result_display_until_ms: int = 0

    # Hand tracking state
    prev_fist_y: Optional[float] = None
    fist_motion_active: bool = False


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
                max_num_hands=1,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5
            )
            self.enabled = True
        except ImportError:
            print("Warning: mediapipe not found. Fist detection disabled.")
            self.enabled = False
            self.hands = None

        self.prev_fist_y = None
        self.motion_threshold = 0.15  # 15% of screen height
        self.fist_detected_current_frame = False

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

    def detect_pull_motion(self, frame) -> bool:
        """Detect downward fist motion (lever pull)"""
        if not self.enabled or self.hands is None:
            return False

        self.fist_detected_current_frame = False

        try:
            imgRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(imgRGB)

            if not results.multi_hand_landmarks:
                self.prev_fist_y = None
                return False

            for hand_landmarks in results.multi_hand_landmarks:
                # Check if fist is closed
                if not self.is_fist_closed(hand_landmarks):
                    self.prev_fist_y = None
                    continue

                self.fist_detected_current_frame = True

                # Get current wrist position (landmark 0)
                current_y = hand_landmarks.landmark[0].y

                # Detect downward motion
                if self.prev_fist_y is not None:
                    delta_y = current_y - self.prev_fist_y

                    # If moved down significantly, trigger pull
                    if delta_y > self.motion_threshold:
                        self.prev_fist_y = None
                        return True

                self.prev_fist_y = current_y

        except Exception as e:
            print(f"Fist detection error: {e}")

        return False


def generate_symbol_images() -> Dict[str, pygame.Surface]:
    """Generate slot symbols programmatically"""
    symbols = {}

    # Seven (red on black)
    seven = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT))
    seven.fill((20, 0, 0))
    font = pygame.font.SysFont('georgia', 70, bold=True)
    text = font.render('7', True, (255, 0, 0))
    text_rect = text.get_rect(center=(SYMBOL_HEIGHT // 2, SYMBOL_HEIGHT // 2))
    seven.blit(text, text_rect)
    # Add glow effect
    glow_surf = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT), pygame.SRCALPHA)
    pygame.draw.circle(glow_surf, (255, 0, 0, 50), (SYMBOL_HEIGHT // 2, SYMBOL_HEIGHT // 2), 40)
    seven.blit(glow_surf, (0, 0))
    symbols['seven'] = seven

    # BAR (gold on black)
    bar = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT))
    bar.fill((20, 10, 0))
    pygame.draw.rect(bar, NEON_GOLD, (15, 40, 70, 20), border_radius=3)
    font = pygame.font.SysFont('arial', 18, bold=True)
    text = font.render('BAR', True, (0, 0, 0))
    text_rect = text.get_rect(center=(50, 50))
    bar.blit(text, text_rect)
    symbols['bar'] = bar

    # Cherry (red fruit)
    cherry = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT))
    cherry.fill((20, 0, 0))
    pygame.draw.circle(cherry, (220, 20, 60), (50, 55), 25)
    pygame.draw.circle(cherry, (139, 0, 0), (50, 55), 25, 3)
    # Stem
    pygame.draw.line(cherry, (0, 100, 0), (50, 30), (50, 35), 3)
    symbols['cherry'] = cherry

    # Lemon (yellow fruit)
    lemon = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT))
    lemon.fill((20, 10, 0))
    pygame.draw.ellipse(lemon, (255, 255, 0), (25, 35, 50, 30))
    pygame.draw.ellipse(lemon, (180, 180, 0), (25, 35, 50, 30), 3)
    symbols['lemon'] = lemon

    # Orange (orange fruit)
    orange = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT))
    orange.fill((20, 10, 0))
    pygame.draw.circle(orange, (255, 140, 0), (50, 50), 28)
    pygame.draw.circle(orange, (200, 100, 0), (50, 50), 28, 3)
    symbols['orange'] = orange

    # Watermelon (green/red fruit)
    watermelon = pygame.Surface((SYMBOL_HEIGHT, SYMBOL_HEIGHT))
    watermelon.fill((20, 10, 0))
    # Green rind
    pygame.draw.circle(watermelon, (34, 139, 34), (50, 50), 30)
    # Red center
    pygame.draw.circle(watermelon, (255, 0, 0), (50, 50), 22)
    # Seeds
    for x, y in [(45, 45), (55, 45), (50, 55)]:
        pygame.draw.circle(watermelon, (0, 0, 0), (x, y), 2)
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


def draw_reel(surface: pygame.Surface, reel: Reel, x: int, y: int,
              symbol_images: Dict[str, pygame.Surface]):
    """Draw a single reel with animation"""
    # Draw reel background
    reel_rect = pygame.Rect(x, y, REEL_WIDTH, REEL_HEIGHT)
    pygame.draw.rect(surface, REEL_BG, reel_rect, border_radius=12)
    pygame.draw.rect(surface, REEL_BORDER, reel_rect, width=4, border_radius=12)

    # Create clipping region
    clip_rect = surface.get_clip()
    surface.set_clip(reel_rect)

    # Draw symbols (show 3 symbols)
    final_idx = reel.symbols.index(reel.final_symbol)
    symbols_to_draw = [
        reel.symbols[(final_idx - 1) % len(reel.symbols)],
        reel.final_symbol,
        reel.symbols[(final_idx + 1) % len(reel.symbols)]
    ]

    for i, symbol in enumerate(symbols_to_draw):
        img = symbol_images[symbol]
        pos_y = y + (i * SYMBOL_HEIGHT) + SYMBOL_HEIGHT - reel.current_offset

        # Center horizontally in reel
        pos_x = x + (REEL_WIDTH - SYMBOL_HEIGHT) // 2

        # Apply motion blur if spinning
        if reel.state == ReelState.SPINNING:
            # Create blurred version
            blurred = img.copy()
            blurred.set_alpha(150)
            surface.blit(blurred, (pos_x, pos_y))
        else:
            surface.blit(img, (pos_x, pos_y))

    surface.set_clip(clip_rect)


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

    # Score
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

    # Result message
    msg_font = pygame.font.SysFont('georgia', 32, bold=True)
    msg_color = NEON_GOLD if "JACKPOT" in state.result_message else TEXT_CREAM
    msg_surface = msg_font.render(state.result_message, True, msg_color)
    msg_rect = msg_surface.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 80))
    surface.blit(msg_surface, msg_rect)


def can_trigger_spin(state: SlotMachineState, now_ms: int) -> bool:
    """Check if spin can be triggered"""
    return (state.phase == GamePhase.IDLE and
            now_ms >= state.input_cooldown_until_ms)


def start_spin(state: SlotMachineState, now_ms: int):
    """Start spinning the reels"""
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


def update_game(state: SlotMachineState, now_ms: int):
    """Update game logic each frame"""
    if state.phase == GamePhase.SPINNING:
        # Update each reel
        for reel in state.reels:
            if reel.state == ReelState.SPINNING:
                # Scroll animation
                reel.current_offset += 30
                if reel.current_offset >= SYMBOL_HEIGHT:
                    reel.current_offset -= SYMBOL_HEIGHT

                # Check if should stop
                if now_ms >= reel.stop_time_ms:
                    reel.state = ReelState.STOPPING

            elif reel.state == ReelState.STOPPING:
                # Ease to final position
                reel.current_offset *= 0.85
                if abs(reel.current_offset) < 1:
                    reel.current_offset = 0
                    reel.state = ReelState.STOPPED

        # Check if all stopped
        if all(r.state == ReelState.STOPPED for r in state.reels):
            check_win(state, now_ms)

    elif state.phase == GamePhase.RESULT_DISPLAY:
        # Wait 2 seconds then return to idle
        if now_ms >= state.result_display_until_ms:
            state.phase = GamePhase.IDLE
            state.result_message = "Pull the lever!"


def check_win(state: SlotMachineState, now_ms: int):
    """Check for winning combinations"""
    symbols = [reel.final_symbol for reel in state.reels]

    # 3 matching sevens (JACKPOT)
    if symbols[0] == symbols[1] == symbols[2] == 'seven':
        state.score += 500
        state.jackpots += 1
        state.result_message = "🎰 JACKPOT! 777! +500 🎰"

    # 3 matching BARs
    elif symbols[0] == symbols[1] == symbols[2] == 'bar':
        state.score += 100
        state.result_message = "⭐ THREE BARS! +100 ⭐"

    # 3 matching fruits
    elif symbols[0] == symbols[1] == symbols[2]:
        state.score += 50
        state.result_message = f"✨ THREE {symbols[0].upper()}S! +50 ✨"

    # 2 matching
    elif (symbols[0] == symbols[1] or
          symbols[1] == symbols[2] or
          symbols[0] == symbols[2]):
        state.score += 10
        state.result_message = "Two Match! +10"

    # No match
    else:
        state.result_message = "No match. Try again!"

    state.phase = GamePhase.RESULT_DISPLAY
    state.result_display_until_ms = now_ms + 2000


def render_game(surface: pygame.Surface, state: SlotMachineState,
                symbol_images: Dict[str, pygame.Surface]):
    """Render the game"""
    # Background
    draw_gradient_background(surface)

    # UI
    draw_ui(surface, state)

    # Calculate reel positions (centered)
    total_reel_width = (NUM_REELS * REEL_WIDTH) + ((NUM_REELS - 1) * REEL_SPACING)
    start_x = (WINDOW_WIDTH - total_reel_width) // 2
    reels_y = 200

    # Draw reels
    for i, reel in enumerate(state.reels):
        reel_x = start_x + (i * (REEL_WIDTH + REEL_SPACING))
        draw_reel(surface, reel, reel_x, reels_y, symbol_images)

    # Scanlines overlay
    draw_scanlines(surface)


def main():
    """Main game loop"""
    # Initialize pygame
    pygame.init()
    os.environ['SDL_VIDEO_WINDOW_POS'] = "700,100"
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption('Slot Machine 1950s Vegas')
    clock = pygame.time.Clock()

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
    print("Controls: Pull fist down or press SPACEBAR to spin")
    print("Press ESC to quit")

    while running:
        now_ms = pygame.time.get_ticks()

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                # Spacebar to spin
                if event.key == pygame.K_SPACE:
                    if can_trigger_spin(state, now_ms):
                        start_spin(state, now_ms)
                        state.input_cooldown_until_ms = now_ms + 2000

        # Process webcam frame
        success, frame = cam.read()
        if success:
            frame = cv2.flip(frame, 1)

            # Check fist pull motion
            pull_detected = fist_detector.detect_pull_motion(frame)

            if pull_detected and can_trigger_spin(state, now_ms):
                start_spin(state, now_ms)
                state.input_cooldown_until_ms = now_ms + 2000

            # Draw debug info on CV window
            status_text = "READY" if can_trigger_spin(state, now_ms) else "COOLDOWN"
            cv2.putText(frame, f"Status: {status_text}",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, "Pull fist down to spin!",
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, "(Or press SPACEBAR)",
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            if fist_detector.fist_detected_current_frame:
                cv2.putText(frame, "FIST DETECTED!",
                           (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            cv2.imshow("Slot Machine Controls", frame)
            cv2.waitKey(1)

        # Update game state
        update_game(state, now_ms)

        # Render
        render_game(screen, state, symbol_images)
        pygame.display.flip()
        clock.tick(FPS)

    # Cleanup
    cam.release()
    cv2.destroyAllWindows()
    pygame.quit()
    print(f"Game Over! Final Score: {state.score}")
    print(f"Total Spins: {state.total_spins}, Jackpots: {state.jackpots}")


if __name__ == '__main__':
    main()
