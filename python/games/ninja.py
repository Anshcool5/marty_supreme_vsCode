# ============== #
# main stuff now #
# ============== #

import argparse
import os
import cv2
import mediapipe as mp
import time, random, math
import numpy as np
import pygame

# ---- Game constants ----
W, H = 960, 540
GRAVITY = 1200.0          # px/s^2
SPAWN_EVERY = 0.9         # seconds
SLICE_SPEED_THRESH = 1400 # px/s
FRUIT_RADIUS = 28
MAX_FRUITS = 6
MULT_DURATION = 5.0       # seconds of 2x multiplier

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.normpath(os.path.join(HERE, "..", "assets", "ninja"))
WINDOW_TITLE = "Fruit Slayer"
PREVIEW_TITLE = "Fruit Slayer Camera Debug"

SLICE_SFX = None
EXPLOSION_SFX = None
AUDIO_READY = False
AUDIO_WARNING_EMITTED = False

REQUIRED_PNGS = [
    "strawberry.png",
    "mango.png",
    "pineapple.png",
    "watermelon.png",
    "score_2x_banana.png",
    "plum.png",
    "coconut.png",
    "bomb.png",
]
REQUIRED_AUDIO = ["slice.wav", "explosion.wav"]
REQUIRED_OTHER = ["background.jpeg"]

# ---- Helpers ----
def validate_assets():
    required = REQUIRED_PNGS + REQUIRED_AUDIO + REQUIRED_OTHER
    missing = [name for name in required if not os.path.isfile(os.path.join(ASSET_DIR, name))]
    if missing:
        listed = "\n".join(f"- {name}" for name in missing)
        raise FileNotFoundError(
            f"Missing required ninja assets in: {ASSET_DIR}\n{listed}"
        )

def load_png(name):
    """Load a PNG with alpha, ensure 4 channels, or raise helpful error."""
    path = os.path.join(ASSET_DIR, name)
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(
            f"Asset not found or unreadable: {path}\n"
            f"Working dir: {os.getcwd()}\n"
            f"Tip: ensure the file exists and the path is correct."
        )
    if img.ndim == 3 and img.shape[2] == 3:
        alpha = 255 * np.ones((img.shape[0], img.shape[1], 1), dtype=img.dtype)
        img = np.concatenate([img, alpha], axis=2)
    return img

def overlay_img(bg, fg, x, y):
    """Alpha-blend fg (4ch) onto bg (3ch), centered at (x,y). Handles edges safely."""
    fh, fw = fg.shape[:2]
    Hh, Ww = bg.shape[:2]

    x1 = int(round(x - fw / 2)); y1 = int(round(y - fh / 2))
    x2 = x1 + fw;                 y2 = y1 + fh

    bx1 = max(0, x1); by1 = max(0, y1)
    bx2 = min(Ww, x2); by2 = min(Hh, y2)
    if bx1 >= bx2 or by1 >= by2:
        return bg

    fx1 = bx1 - x1; fy1 = by1 - y1
    fx2 = fx1 + (bx2 - bx1); fy2 = fy1 + (by2 - by1)

    fg_crop = fg[fy1:fy2, fx1:fx2]
    bg_roi  = bg[by1:by2, bx1:bx2]
    if fg_crop.size == 0 or bg_roi.size == 0:
        return bg

    alpha = (fg_crop[:, :, 3:4] / 255.0)  # (h,w,1)
    bg[by1:by2, bx1:bx2] = alpha * fg_crop[:, :, :3] + (1.0 - alpha) * bg_roi
    return bg

def load_background():
    path = os.path.join(ASSET_DIR, "background.jpeg")
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        print(f"[ninja] Warning: failed to load background: {path}. Falling back to solid color.")
        return np.full((H, W, 3), (18, 18, 26), dtype=np.uint8)
    return cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)

def init_audio():
    global SLICE_SFX, EXPLOSION_SFX, AUDIO_READY, AUDIO_WARNING_EMITTED
    if AUDIO_READY:
        return

    try:
        pygame.mixer.init()
        SLICE_SFX = pygame.mixer.Sound(os.path.join(ASSET_DIR, "slice.wav"))
        EXPLOSION_SFX = pygame.mixer.Sound(os.path.join(ASSET_DIR, "explosion.wav"))
        AUDIO_READY = True
    except Exception as error:
        if not AUDIO_WARNING_EMITTED:
            print(f"[ninja] Warning: audio disabled: {error}")
            AUDIO_WARNING_EMITTED = True
        AUDIO_READY = False
        SLICE_SFX = None
        EXPLOSION_SFX = None

def play_slice_sfx():
    if AUDIO_READY and SLICE_SFX is not None:
        SLICE_SFX.play()

def play_explosion_sfx():
    if AUDIO_READY and EXPLOSION_SFX is not None:
        EXPLOSION_SFX.play()

# ---- Assets ----
fruit_imgs = {}
hud_icon = None

# ---- Game logic ----
class Fruit:
    TYPES = ["red","orange","yellow","green","blue","purple","brown"]
    def __init__(self, now, bomb_prob=0.12):
        self.x = random.randint(int(0.15*W), int(0.85*W))
        self.y = H + FRUIT_RADIUS + 5
        self.vx = random.uniform(-220, 220)
        self.vy = -random.uniform(700, 1300)
        self.alive = True
        self.born = now
        if random.random() < bomb_prob:
            self.key = "bomb"; self.is_bomb = True
        else:
            self.key = random.choice(Fruit.TYPES); self.is_bomb = False

    def update(self, dt):
        if not self.alive: return
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y - FRUIT_RADIUS > H + 80:
            self.alive = False

def seg_circle_intersects(x1,y1,x2,y2, cx,cy,r):
    dx, dy = x2-x1, y2-y1
    if dx==0 and dy==0:
        return math.hypot(cx-x1, cy-y1) <= r
    t = ((cx-x1)*dx + (cy-y1)*dy) / (dx*dx + dy*dy)
    t = max(0.0, min(1.0, t))
    px, py = x1 + t*dx, y1 + t*dy
    return (cx - px)**2 + (cy - py)**2 <= r*r

def parse_args():
    parser = argparse.ArgumentParser(description="Fruit Slayer with hand tracking")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index")
    parser.add_argument(
        "--show-preview",
        action="store_true",
        help="Show a debug camera preview window (off by default)",
    )
    return parser.parse_args()

def main():
    global fruit_imgs, hud_icon
    args = parse_args()
    validate_assets()
    init_audio()

    fruit_imgs = {
        "red": load_png("strawberry.png"),
        "orange": load_png("mango.png"),
        "yellow": load_png("pineapple.png"),
        "green": load_png("watermelon.png"),
        "blue": load_png("score_2x_banana.png"),
        "purple": load_png("plum.png"),
        "brown": load_png("coconut.png"),
        "bomb": load_png("bomb.png"),
    }
    hud_icon = load_png("watermelon.png")

    cap = cv2.VideoCapture(args.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    if not cap.isOpened():
        print("Could not open camera"); return

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    background = load_background()

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    if args.show_preview:
        cv2.namedWindow(PREVIEW_TITLE, cv2.WINDOW_NORMAL)

    fruits = []
    score = 0
    last_spawn = 0.0
    last_t = time.time()

    last_tip = None
    last_tip_time = None

    bomb_flash_until = 0.0
    score_mult_until = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (W, H))
            frame = cv2.flip(frame, 1)

            now = time.time()
            dt = now - last_t
            last_t = now

            if now - last_spawn > SPAWN_EVERY and sum(f.alive for f in fruits) < MAX_FRUITS:
                bomb_prob = 0.1 + min(0.3, score * 0.01)  # 10% -> 40% max
                fruits.append(Fruit(now, bomb_prob=bomb_prob))
                last_spawn = now

            for f in fruits:
                f.update(dt)

            debug_frame = frame.copy() if args.show_preview else None

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)

            slice_segment = None
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0]
                tip = lm.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                x, y = int(tip.x * W), int(tip.y * H)

                if last_tip is not None and last_tip_time is not None:
                    dt_tip = now - last_tip_time
                    if dt_tip > 0:
                        speed = math.hypot(x - last_tip[0], y - last_tip[1]) / dt_tip
                        if speed > SLICE_SPEED_THRESH:
                            slice_segment = (last_tip[0], last_tip[1], x, y)

                last_tip = (x, y)
                last_tip_time = now

                if debug_frame is not None:
                    cv2.circle(debug_frame, (x, y), 7, (255, 255, 255), -1)
                    mp.solutions.drawing_utils.draw_landmarks(
                        debug_frame, lm, mp_hands.HAND_CONNECTIONS
                    )

            if slice_segment:
                x1, y1, x2, y2 = slice_segment
                for f in fruits:
                    if f.alive and seg_circle_intersects(
                        x1, y1, x2, y2, int(f.x), int(f.y), FRUIT_RADIUS
                    ):
                        f.alive = False
                        if getattr(f, "is_bomb", False):
                            score = max(0, score - 5)
                            bomb_flash_until = now + 0.20
                            play_explosion_sfx()
                        else:
                            base = 1
                            if f.key == "blue":  # 2x banana
                                score_mult_until = max(score_mult_until, now) + MULT_DURATION
                            mult = 2 if now < score_mult_until else 1
                            score += base * mult
                            play_slice_sfx()

            game_frame = background.copy()
            if slice_segment:
                x1, y1, x2, y2 = slice_segment
                cv2.line(game_frame, (x1, y1), (x2, y2), (255, 255, 255), 2)

            for f in fruits:
                if not f.alive:
                    continue
                img = fruit_imgs.get(f.key)
                if img is None:
                    cv2.circle(game_frame, (int(f.x), int(f.y)), FRUIT_RADIUS, (0, 255, 0), -1)
                    continue
                scale = (2 * FRUIT_RADIUS) / img.shape[0]
                new_w = int(img.shape[1] * scale)
                new_h = int(img.shape[0] * scale)
                fg = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                game_frame = overlay_img(game_frame, fg, int(f.x), int(f.y))

            fruits = [f for f in fruits if f.alive or (now - f.born) < 8.0]

            if now < bomb_flash_until:
                overlay = game_frame.copy()
                cv2.rectangle(overlay, (0, 0), (W, H), (0, 0, 255), -1)
                game_frame = cv2.addWeighted(overlay, 0.25, game_frame, 0.75, 0)

            ICON_H = 36
            scale = ICON_H / hud_icon.shape[0]
            icon_w = int(hud_icon.shape[1] * scale)
            icon_h = int(hud_icon.shape[0] * scale)
            icon_resized = cv2.resize(hud_icon, (icon_w, icon_h), interpolation=cv2.INTER_AREA)
            MARGIN = 12
            game_frame = overlay_img(
                game_frame, icon_resized, MARGIN + icon_w // 2, MARGIN + icon_h // 2
            )

            text = f"{score}"
            tx = MARGIN + icon_w + 8
            ty = MARGIN + icon_h - 6
            cv2.putText(
                game_frame, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 3, cv2.LINE_AA
            )
            cv2.putText(
                game_frame,
                text,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.1,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )

            remaining = score_mult_until - now
            if remaining > 0:
                bx = tx + 60
                by = ty
                cv2.putText(
                    game_frame, "x2", (bx, by), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3, cv2.LINE_AA
                )
                cv2.putText(
                    game_frame,
                    "x2",
                    (bx, by),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 215, 255),
                    2,
                    cv2.LINE_AA,
                )

            cv2.imshow(WINDOW_TITLE, game_frame)
            if debug_frame is not None:
                if slice_segment:
                    x1, y1, x2, y2 = slice_segment
                    cv2.line(debug_frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
                cv2.imshow(PREVIEW_TITLE, debug_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
    finally:
        cap.release()
        hands.close()
        cv2.destroyAllWindows()
        if AUDIO_READY:
            pygame.mixer.quit()

if __name__ == "__main__":
    main()
