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
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple

import pygame


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


class Phase(str, Enum):
    BETTING = "BETTING"
    PLAYER_TURN = "PLAYER_TURN"
    DEALER_TURN = "DEALER_TURN"
    ROUND_END = "ROUND_END"


class RoundResult(str, Enum):
    NONE = "NONE"
    WIN = "WIN"
    LOSE = "LOSE"
    PUSH = "PUSH"
    BLACKJACK_WIN = "BLACKJACK_WIN"


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
class GameState:
    bankroll: int
    min_bet: int = MIN_BET
    current_bet: int = MIN_BET
    phase: Phase = Phase.BETTING
    round_result: RoundResult = RoundResult.NONE
    message: str = "Place your bet and click Deal."
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    player_hand: Hand = field(default_factory=Hand)
    dealer_hand: Hand = field(default_factory=Hand)
    deck: Deck = field(default_factory=Deck)
    can_start_new_round: bool = True

    def reset_for_next_round(self) -> None:
        self.player_hand = Hand()
        self.dealer_hand = Hand()
        self.round_result = RoundResult.NONE
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

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        fill = (48, 114, 77) if self.enabled else (90, 90, 90)
        border = (235, 225, 200) if self.enabled else (140, 140, 140)
        text_color = (250, 250, 250) if self.enabled else (190, 190, 190)
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


def deal_initial_cards(state: GameState) -> None:
    state.player_hand = Hand()
    state.dealer_hand = Hand()
    state.player_hand.add(state.deck.draw())
    state.dealer_hand.add(state.deck.draw())
    state.player_hand.add(state.deck.draw())
    state.dealer_hand.add(state.deck.draw())


def settle_round(state: GameState, result: RoundResult) -> None:
    bet = state.current_bet
    state.round_result = result
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


def resolve_natural_blackjacks(state: GameState) -> bool:
    player_bj = state.player_hand.is_blackjack()
    dealer_bj = state.dealer_hand.is_blackjack()
    if player_bj and dealer_bj:
        settle_round(state, RoundResult.PUSH)
        return True
    if player_bj:
        settle_round(state, RoundResult.BLACKJACK_WIN)
        return True
    if dealer_bj:
        settle_round(state, RoundResult.LOSE)
        return True
    return False


def dealer_play(state: GameState) -> None:
    state.phase = Phase.DEALER_TURN
    while True:
        total, _ = state.dealer_hand.value()
        if total < 17:
            state.dealer_hand.add(state.deck.draw())
        else:
            break


def compare_hands(state: GameState) -> None:
    player_total, _ = state.player_hand.value()
    dealer_total, _ = state.dealer_hand.value()
    if dealer_total > 21:
        settle_round(state, RoundResult.WIN)
        return
    if player_total > dealer_total:
        settle_round(state, RoundResult.WIN)
    elif player_total < dealer_total:
        settle_round(state, RoundResult.LOSE)
    else:
        settle_round(state, RoundResult.PUSH)


def draw_cards(
    surface: pygame.Surface,
    images: Dict[str, pygame.Surface],
    hand: Hand,
    start_x: int,
    y: int,
    hide_second: bool = False,
) -> None:
    for idx, card in enumerate(hand.cards):
        x = start_x + idx * (CARD_WIDTH + CARD_GAP)
        key = "card_back.png" if hide_second and idx == 1 else card.image_key
        surface.blit(images[key], (x, y))


def build_buttons(state: GameState) -> Dict[str, Button]:
    buttons: Dict[str, Button] = {}
    if state.phase == Phase.BETTING:
        buttons["dec"] = Button(pygame.Rect(80, 600, 120, 48), "- Bet")
        buttons["inc"] = Button(pygame.Rect(220, 600, 120, 48), "+ Bet")
        buttons["deal"] = Button(pygame.Rect(360, 600, 140, 48), "Deal")
        buttons["dec"].enabled = state.current_bet > state.min_bet
        buttons["inc"].enabled = state.current_bet + BET_STEP <= state.max_bet
        buttons["deal"].enabled = state.current_bet <= state.max_bet and state.max_bet >= state.min_bet
    elif state.phase == Phase.PLAYER_TURN:
        buttons["hit"] = Button(pygame.Rect(80, 600, 140, 48), "Hit")
        buttons["stand"] = Button(pygame.Rect(240, 600, 140, 48), "Stand")
    elif state.phase == Phase.ROUND_END:
        buttons["next"] = Button(pygame.Rect(80, 600, 190, 48), "Next Round")
        buttons["quit"] = Button(pygame.Rect(290, 600, 140, 48), "Quit")
        buttons["next"].enabled = state.can_start_new_round
    return buttons


def render(surface: pygame.Surface, state: GameState, images: Dict[str, pygame.Surface]) -> Dict[str, Button]:
    surface.fill((22, 92, 64))
    header_font = pygame.font.SysFont("georgia", 34, bold=True)
    text_font = pygame.font.SysFont("georgia", 24)
    small_font = pygame.font.SysFont("georgia", 20)

    title = header_font.render("BLACKJACK", True, (245, 238, 215))
    surface.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, 20))

    stats = (
        f"Bankroll: {state.bankroll}    Bet: {state.current_bet}    "
        f"W/L/P: {state.wins}/{state.losses}/{state.pushes}"
    )
    surface.blit(text_font.render(stats, True, (235, 235, 235)), (40, 75))

    dealer_total, _ = state.dealer_hand.value()
    player_total, _ = state.player_hand.value()
    hide_hole = state.phase == Phase.PLAYER_TURN
    dealer_value_text = "?" if hide_hole else str(dealer_total)
    surface.blit(text_font.render(f"Dealer ({dealer_value_text})", True, (245, 245, 245)), (40, 130))
    surface.blit(text_font.render(f"Player ({player_total})", True, (245, 245, 245)), (40, 390))

    draw_cards(surface, images, state.dealer_hand, start_x=40, y=170, hide_second=hide_hole)
    draw_cards(surface, images, state.player_hand, start_x=40, y=430)

    message_surf = small_font.render(state.message, True, (250, 240, 210))
    surface.blit(message_surf, (40, 350))

    buttons = build_buttons(state)
    for button in buttons.values():
        button.draw(surface, text_font)

    pygame.display.flip()
    return buttons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GUI Blackjack (pygame)")
    parser.add_argument("--bankroll", type=int, default=DEFAULT_BANKROLL, help="Starting bankroll")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Frame rate cap")
    return parser.parse_args()


def run_game(start_bankroll: int, fps: int) -> int:
    if start_bankroll <= 0:
        print("Starting bankroll must be > 0", file=sys.stderr)
        return 2
    if fps <= 0:
        print("FPS must be > 0", file=sys.stderr)
        return 2

    pygame.init()
    pygame.display.set_caption("Blackjack")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    assets_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "cards", "large_cards")
    )
    try:
        card_images = load_card_images(assets_dir)
    except RuntimeError as exc:
        pygame.quit()
        print(str(exc), file=sys.stderr)
        return 1

    state = GameState(bankroll=start_bankroll)
    state.current_bet = max(MIN_BET, min(start_bankroll, 100))
    state.can_start_new_round = state.bankroll >= state.min_bet
    if not state.can_start_new_round:
        state.phase = Phase.ROUND_END
        state.message = "Game over: bankroll below minimum bet."

    running = True
    while running:
        buttons = render(screen, state, card_images)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if state.phase == Phase.BETTING:
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
                            deal_initial_cards(state)
                            state.phase = Phase.PLAYER_TURN
                            state.message = "Your turn: Hit or Stand."
                            resolve_natural_blackjacks(state)
                elif state.phase == Phase.PLAYER_TURN:
                    if "hit" in buttons and buttons["hit"].contains(pos):
                        state.player_hand.add(state.deck.draw())
                        if state.player_hand.is_bust():
                            settle_round(state, RoundResult.LOSE)
                        else:
                            state.message = "Your turn: Hit or Stand."
                    elif "stand" in buttons and buttons["stand"].contains(pos):
                        dealer_play(state)
                        compare_hands(state)
                elif state.phase == Phase.ROUND_END:
                    if "next" in buttons and buttons["next"].contains(pos):
                        state.reset_for_next_round()
                    elif "quit" in buttons and buttons["quit"].contains(pos):
                        running = False
                        break
        clock.tick(fps)

    pygame.quit()
    return 0


def main() -> int:
    args = parse_args()
    return run_game(start_bankroll=args.bankroll, fps=args.fps)


if __name__ == "__main__":
    raise SystemExit(main())
