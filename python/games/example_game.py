#!/usr/bin/env python3
"""
Example Game for Marty Supreme
Demonstrates the game communication protocol and basic computer vision setup
"""

import sys
import os

# Add parent directory to path to import game_base
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib.game_base import GameBase
import numpy as np

# Try to import OpenCV (optional for this example)
try:
    import cv2
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False


class ExampleGame(GameBase):
    """
    A simple example game that demonstrates:
    - Communication with the VSCode extension
    - Basic state management
    - Computer vision capabilities (if OpenCV is installed)
    """

    def __init__(self):
        super().__init__()
        self.score = 0
        self.moves = 0
        self.player_name = "Player"

    def initialize(self, config):
        """Initialize the game with configuration from the extension"""
        self.log_info("Initializing example game...")

        # Get player name from config if provided
        self.player_name = config.get('player_name', 'Player')
        message = config.get('message', 'No message')

        self.log_info(f"Player: {self.player_name}")
        self.log_info(f"Message from extension: {message}")

        # Check OpenCV availability
        if CV_AVAILABLE:
            self.log_info(f"OpenCV version: {cv2.__version__}")
            self.log_info("Computer vision capabilities: AVAILABLE")

            # Create a simple test image
            test_image = np.zeros((100, 100, 3), dtype=np.uint8)
            test_image[25:75, 25:75] = [0, 255, 0]  # Green square
            self.log_info("Created test image: 100x100 with green square")
        else:
            self.log_info("Computer vision capabilities: NOT AVAILABLE (OpenCV not installed)")
            self.log_info("Install with: pip install opencv-python")

        return {
            'player_name': self.player_name,
            'cv_available': CV_AVAILABLE,
            'message': 'Example game initialized successfully!'
        }

    def process_input(self, input_data):
        """Process input from the extension"""
        action = input_data.get('action', 'unknown')
        self.log_info(f"Processing action: {action}")

        self.moves += 1

        if action == 'increase_score':
            amount = input_data.get('amount', 1)
            self.score += amount
            self.log_info(f"Score increased by {amount}")

        elif action == 'decrease_score':
            amount = input_data.get('amount', 1)
            self.score -= amount
            self.log_info(f"Score decreased by {amount}")

        elif action == 'reset':
            self.score = 0
            self.moves = 0
            self.log_info("Game reset")

        elif action == 'cv_demo' and CV_AVAILABLE:
            # Demonstrate computer vision
            img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_count = np.count_nonzero(edges)

            self.log_info(f"CV Demo: Processed 100x100 image, found {edge_count} edge pixels")

            return {
                'action': action,
                'cv_result': {
                    'edge_count': int(edge_count),
                    'image_size': [100, 100]
                }
            }

        else:
            self.log_info(f"Unknown action: {action}")

        return {
            'action': action,
            'score': self.score,
            'moves': self.moves
        }

    def get_state(self):
        """Return current game state"""
        return {
            'player_name': self.player_name,
            'score': self.score,
            'moves': self.moves,
            'cv_available': CV_AVAILABLE
        }

    def cleanup(self):
        """Cleanup when game ends"""
        self.log_info("Cleaning up example game...")
        self.log_info(f"Final score: {self.score}")
        self.log_info(f"Total moves: {self.moves}")


if __name__ == '__main__':
    # Create and run the game
    game = ExampleGame()
    game.run()
