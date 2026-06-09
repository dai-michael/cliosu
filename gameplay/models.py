from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from collections import deque


class Judgement(Enum):
    MX = auto()
    PERFECT = auto()
    GREAT = auto()
    GOOD = auto()
    BAD = auto()
    MISS = auto()


JUDGEMENT_ORDER: tuple[Judgement, ...] = (
    Judgement.MX,
    Judgement.PERFECT,
    Judgement.GREAT,
    Judgement.GOOD,
    Judgement.BAD,
)


@dataclass
class ManiaObject:
    start_time: float  # seconds since song start
    column: int
    end_time: float  # seconds since song start
    hit_time: float | None = None
    release_time: float | None = None
    head_judgement: Judgement | None = None
    tail_judgement: Judgement | None = None

    @property
    def is_slider(self) -> bool:
        return self.end_time != self.start_time

@dataclass
class ManiaMapState:
    od: int
    num_keys: int
    upcoming: deque[ManiaObject] = field(default_factory=deque)

# Things for input handler
@dataclass
class GameInput:
    column: int
    pressed_at: float = 0.0
    used: bool = False


class ControlAction(Enum):
    PAUSE = auto()
    RESTART = auto()
    QUIT = auto()

@dataclass
class ControlInput:
    action: ControlAction

# Things for renderer
@dataclass
class RenderM:
    """Screen position for a hitobject.

    start_y and end_y use half-row units: terminal row = y // 2,
    vertical half = y % 2 (0 = top, 1 = bottom).
    """
    start_y: int
    column: int
    end_y: int 

    @property
    def is_slider(self) -> bool:
        return self.end_y != self.start_y

@dataclass
class GameStats:
    accuracy: float
    combo: int

@dataclass
class Settings:
    keybinds: dict[str,GameInput | ControlInput]
    scroll_speed: int
    window_height: int = 40
    window_width: int = 100

@dataclass
class Results:
    accuracy: float = 100
    combo: int = 0
    max_combo: int = 0
    mx: int = 0
    perfect: int = 0
    great: int = 0
    good: int = 0
    bad: int = 0
    miss: int = 0
    play_date: datetime = datetime.now()
    hitobjects: list[ManiaObject] = field(default_factory=list)
    slider_breaks: int = 0
    tot_objects: int = 0
    player: str | None = None