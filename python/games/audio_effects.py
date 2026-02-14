#!/usr/bin/env python3
"""Shared random boot/win/lose SFX loader for Marty Supreme pygame games."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Optional

import pygame


class GameAudioEffects:
    def __init__(self, root_dir: Optional[Path] = None, volume: float = 1.0) -> None:
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent / "assets" / "audio_effects"
        self.root_dir = root_dir
        self.volume = volume
        self._clips: Dict[str, List[Path]] = {}
        self._last_sound: Optional[pygame.mixer.Sound] = None
        self.enabled = self._ensure_mixer()

    def _ensure_mixer(self) -> bool:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            return True
        except pygame.error:
            return False

    def _load_folder(self, category: str) -> List[Path]:
        if category in self._clips:
            return self._clips[category]

        folder = self.root_dir / category
        if not folder.exists() or not folder.is_dir():
            self._clips[category] = []
            return self._clips[category]

        clips = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".mp3")
        self._clips[category] = clips
        return clips

    def _play_random(self, category: str) -> Optional[Path]:
        if not self.enabled:
            return None

        clips = self._load_folder(category)
        if not clips:
            return None

        selected = random.choice(clips)
        try:
            sound = pygame.mixer.Sound(str(selected))
            sound.set_volume(max(0.0, min(1.0, self.volume)))
            channel = pygame.mixer.find_channel(force=True)
            if channel is None:
                return None
            channel.play(sound)
            self._last_sound = sound
            return selected
        except pygame.error:
            return None

    def play_boot(self) -> Optional[Path]:
        return self._play_random("boot")

    def play_win(self) -> Optional[Path]:
        return self._play_random("win")

    def play_lose(self) -> Optional[Path]:
        return self._play_random("lose")
