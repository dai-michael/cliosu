import threading
import time
import copy
from pynput import keyboard
from gameplay.models import ControlAction, ControlInput, GameInput

class InputHandler:
    """Listens for keyboard inputs and converts them into game events."""
    def __init__(self, key_map: dict[keyboard.KeyCode | keyboard.Key,GameInput | ControlInput]) -> None:
        """
        Takes one argument:
            key_map: A dictionary that maps keyboard keys (KeyCode or Key) to GameInput or ControlInput objects.
        """
        self.key_map = key_map
        self.game_inputs: dict[int, GameInput] = {} # Key is column number
        self.consumed_columns: set[int] = set()
        self.control_inputs: set[ControlAction] = set()
        self._lock = threading.Lock()
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.listener.start()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        action_type = self.key_map.get(key) # If it maps to something
        if action_type is not None:
            if isinstance(action_type, GameInput): # Game input
                column = action_type.column
                with self._lock:
                    if column not in self.game_inputs: # Add input only if it is not being held already
                        self.game_inputs[column] = GameInput(
                            pressed_at=time.perf_counter(),
                            used=False,
                            column=column,
                        )
            elif isinstance(action_type, ControlInput): # Control input
                with self._lock:
                    self.control_inputs.add(action_type.action)

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        action_type = self.key_map.get(key)
        if action_type is not None:
            if isinstance(action_type, GameInput): # Game input
                column = action_type.column
                with self._lock:
                    self.consumed_columns.discard(column)
                    if column in self.game_inputs:
                        self.game_inputs.pop(column) # Release game input

    def mark_consumed(self, column: int) -> None:
        """Mark a column's current press as used until the key is released."""
        with self._lock:
            self.consumed_columns.add(column)

    def poll(self) -> tuple[dict[int, GameInput], set[ControlAction]]:
        with self._lock:
            game_inputs = copy.deepcopy(self.game_inputs)
            for column in self.consumed_columns:
                if column in game_inputs:
                    game_inputs[column].used = True
            control_inputs = set(self.control_inputs)
            self.control_inputs.clear()
            return (game_inputs, control_inputs)