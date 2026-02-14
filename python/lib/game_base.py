"""
Base class for Marty Supreme games
Provides communication protocol and structure for Python-based games
"""

import sys
import json
from abc import ABC, abstractmethod
from typing import Dict, Any


class GameBase(ABC):
    """
    Abstract base class for all Marty Supreme games.

    Games communicate with the VSCode extension via line-delimited JSON:
    - Read commands from stdin (one JSON object per line)
    - Write responses to stdout (one JSON object per line)
    - Write errors/logs to stderr
    """

    def __init__(self):
        self.running = False

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called when the game starts.

        Args:
            config: Configuration dictionary from the extension

        Returns:
            Dictionary with initialization response (status, etc.)
        """
        pass

    @abstractmethod
    def process_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle input from the extension.

        Args:
            input_data: Input data dictionary

        Returns:
            Dictionary with response data
        """
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """
        Get current game state.

        Returns:
            Dictionary representing the current game state
        """
        pass

    @abstractmethod
    def cleanup(self):
        """
        Cleanup resources when game ends.
        """
        pass

    def send_message(self, message: Dict[str, Any]):
        """
        Send a JSON message to the extension via stdout.

        Args:
            message: Dictionary to send
        """
        try:
            json_str = json.dumps(message)
            print(json_str, flush=True)
        except Exception as e:
            self.log_error(f"Failed to send message: {e}")

    def log_error(self, message: str):
        """
        Log an error message to stderr.

        Args:
            message: Error message
        """
        print(f"ERROR: {message}", file=sys.stderr, flush=True)

    def log_info(self, message: str):
        """
        Log an info message to stderr.

        Args:
            message: Info message
        """
        print(f"INFO: {message}", file=sys.stderr, flush=True)

    def run(self):
        """
        Main game loop - reads commands from stdin and processes them.
        """
        self.running = True
        self.log_info("Game started, waiting for commands...")

        try:
            for line in sys.stdin:
                if not self.running:
                    break

                try:
                    command = json.loads(line.strip())
                    self.log_info(f"Received command: {command.get('command', 'unknown')}")

                    response = self.handle_command(command)
                    if response:
                        self.send_message(response)

                except json.JSONDecodeError as e:
                    self.log_error(f"Invalid JSON: {e}")
                    self.send_message({
                        'type': 'error',
                        'message': f'Invalid JSON: {str(e)}'
                    })
                except Exception as e:
                    self.log_error(f"Error processing command: {e}")
                    self.send_message({
                        'type': 'error',
                        'message': str(e)
                    })

        except KeyboardInterrupt:
            self.log_info("Game interrupted by user")
        finally:
            self.cleanup()
            self.log_info("Game ended")

    def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a command from the extension.

        Args:
            command: Command dictionary with 'command' and optional 'data' fields

        Returns:
            Response dictionary
        """
        cmd_type = command.get('command', '')
        data = command.get('data', {})

        if cmd_type == 'initialize':
            result = self.initialize(data)
            return {
                'type': 'initialized',
                'status': 'ok',
                **result
            }

        elif cmd_type == 'input':
            result = self.process_input(data)
            return {
                'type': 'input_processed',
                'status': 'ok',
                **result
            }

        elif cmd_type == 'get_state':
            state = self.get_state()
            return {
                'type': 'state_update',
                'status': 'ok',
                'state': state
            }

        elif cmd_type == 'stop':
            self.running = False
            self.cleanup()
            return {
                'type': 'stopped',
                'status': 'ok'
            }

        else:
            return {
                'type': 'error',
                'message': f'Unknown command: {cmd_type}'
            }
