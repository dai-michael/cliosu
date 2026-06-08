import curses
import time

import vlc

from gameplay.game_renderer import GameRenderer
from gameplay.input_handler import InputHandler
from gameplay.models import (
    GameInput,
    ControlAction,
    GameStats,
    RenderM,
    Settings,
    Results,
    ManiaMapState,
    ManiaObject,
    Judgement,
    JUDGEMENT_ORDER,
)
from input_handler import InputHandler
from game_renderer import GameRenderer
import time
# use vlc music player library to play music
import vlc


def tap_hit_error(note: ManiaObject) -> float | None:
    """Return hit error for a tap note, or None if it was not hit."""
    if note.hit_time is None:
        return None
    return abs(note.hit_time - note.start_time)


def slider_head_hit_error(note: ManiaObject) -> float | None:
    """Return hit error for a slider head, or None if the head was not hit."""
    if note.hit_time is None:
        return None
    return abs(note.hit_time - note.start_time)


def slider_tail_hit_error(note: ManiaObject) -> float | None:
    """Return hit error for a slider tail, or None if the tail was not released."""
    if note.release_time is None:
        return None
    return abs(note.release_time - note.end_time)


def note_judgement_targets(note: ManiaObject) -> list[tuple[str, float | None]]:
    """Return labelled hit errors to judge. Sliders produce separate head and tail targets."""
    if not note.is_slider:
        return [("head", tap_hit_error(note))]
    return [
        ("head", slider_head_hit_error(note)),
        ("tail", slider_tail_hit_error(note)),
    ]


def judgement_for_hit_error(hit_error: float | None, hit_windows: list[float]) -> Judgement:
    """Map hit error to a judgement using ascending hit windows."""
    if hit_error is None or hit_error > hit_windows[-1]:
        return Judgement.MISS

    for judgement, window in zip(JUDGEMENT_ORDER, hit_windows[:-1]):
        if hit_error <= window:
            return judgement

    return Judgement.BAD


class GameEngine:
    def __init__(self, settings: Settings, map_state: ManiaMapState, music_path: str) -> None:
        self.settings = settings
        self.map_state = map_state
        self.music_player = vlc.MediaPlayer(music_path)
        self.start_time = 0
        self.input_handler = InputHandler(self.settings.keybinds)
        self.game_renderer = GameRenderer(curses.initscr(), 4, self.settings.window_height, self.settings.window_width)
        self.visible_notes: list[ManiaObject] = []
        self.tappable_notes: list[RenderM] = [None] * map_state.num_keys
        self.visible_note_window = 10000 / self.settings.scroll_speed
        od = self.map_state.od
        self.hit_windows: list[float] = [
            16 / 1000,
            (64 - 3 * od) / 1000,
            (97 - 3 * od) / 1000,
            (127 - 3 * od) / 1000,
            (151 - 3 * od) / 1000,
            (188 - 3 * od) / 1000,
        ]
        self.results: Results = Results()
        self.curr_judgement = None

    def run(self) -> Results:
        # If time of first note is at start of the song, start frames earlier than the start of the song
        if self.map_state.upcoming[0].start_time < self.visible_note_window:
            audio_playback_delay = self.visible_note_window - self.map_state.upcoming[0].start_time
            early_start_time = time.perf_counter()
            self.start_time = early_start_time + audio_playback_delay
            while time.perf_counter() - early_start_time < audio_playback_delay:
                elapsed = time.perf_counter() - early_start_time
                relative_song_time = elapsed - audio_playback_delay
                self._process_frame(relative_song_time)
        
        # Start music and start gameplay loop again
        self.start_time = time.perf_counter()
        self.music_player.play()
        play = True
        while play:
            relative_song_time = time.perf_counter() - self.start_time
            play = self._process_frame(relative_song_time)


    def _process_frame(self,song_time: float) -> bool:
        """Renders frame at current time in the song
        Accepts negative inputs for song_time"""
        game_inputs, control_inputs = self.input_handler.poll()
        self._convert_input_times(game_inputs)
        # Calculate song time as song time that game_inputs occured at
        # Handle control inputs
        for control_input in control_inputs:
            if control_input.action == ControlAction.QUIT:
                return False
        
        # Process game actions
        self._process_key_presses(game_inputs)
        self._process_key_releases(game_inputs,song_time)
        
        # Update notes lists
        notes_to_judge = self._refresh_active_notes(song_time)
        self._judge_notes(notes_to_judge)

        # Render frame using active notes list
        return True

    def _convert_input_times(self,game_inputs: dict[int, GameInput]) -> None:
        """Modifies game_inputs in place to convert hittime to relative song time"""
        for game_input in game_inputs.values():
            game_input.pressed_at -= self.start_time


    def _process_key_presses(self, game_inputs):
        for column, game_input in game_inputs.items():
            note = self.tappable_notes[column]
            if note is not None and not game_input.used and note.hit_time is None:
                note.hit_time = game_input.pressed_at
                game_input.used = True

    def _process_key_releases(self, game_inputs: dict[int, GameInput], song_time: float) -> None:
        for column, note in enumerate(self.tappable_notes):
            if (
                note is not None
                and note.is_slider
                and note.hit_time is not None
                and note.release_time is None
                and column not in game_inputs
            ):
                note.release_time = song_time

    def _refresh_active_notes(self, song_time: float) -> list[ManiaObject]:
        notes_to_judge = []
        notes_to_judge += self._remove_missed_notes(song_time)
        notes_to_judge += self._remove_hit_notes()

        # Add notes to visible_notes
        self._add_to_visible(song_time)
        # Add notes to tappable_notes
        self._add_to_tappable(song_time)

        return notes_to_judge
    
    def _add_to_tappable(self, song_time:float) -> None:
        latest_tappable_time = song_time + self.hit_windows[-1]
        for note in self.visible_notes:
            if note.start_time < latest_tappable_time:
                if note.column not in self.tappable_notes and note.start_time is None:
                    self.tappable_notes.append(note)

    def _remove_missed_notes(self, curr_song_time: float) -> list[ManiaObject]:
        """
        Arguments: song time
        Returns: list of missed_notes
        Currently handles removal of notes from visible and tappable
        in the future should break into two functions
        """
        to_judge: list[ManiaObject] = []
        for note in list(self.visible_notes):
            time_after_end = curr_song_time - note.end_time
            if time_after_end > self.hit_windows[-1]:
                self.visible_notes.remove(note)
                if (
                    note.column < len(self.tappable_notes)
                    and self.tappable_notes[note.column] is note
                ):
                    self.tappable_notes[note.column] = None
                to_judge.append(note)
        return to_judge
    
    def _judge_notes(self, notes_to_judge: list[ManiaObject]) -> None:
        for note in notes_to_judge:
            self._judge_note(note)

    def _judge_note(self, note: ManiaObject) -> None:
        judgements: list[Judgement] = []

        for part, hit_error in note_judgement_targets(note):
            judgement = judgement_for_hit_error(hit_error, self.hit_windows)
            judgements.append(judgement)

            if part == "head":
                note.head_judgement = judgement
            else:
                note.tail_judgement = judgement

            self._apply_judgement_counter(judgement)

        if (
            note.is_slider
            and note.head_judgement != Judgement.MISS
            and note.tail_judgement == Judgement.MISS
        ):
            self.results.slider_breaks += 1

        self.results.hitobjects.append(note)
        self.curr_judgement = judgements[-1]

    def _apply_judgement_counter(self, judgement: Judgement) -> None:
        counter = judgement.name.lower()
        setattr(self.results, counter, getattr(self.results, counter) + 1)
        self.results.tot_objects += 1

        if judgement == Judgement.MISS:
            self.results.combo = 0
        else:
            self.results.combo += 1
            self.results.max_combo = max(self.results.max_combo, self.results.combo)

    
    def _add_to_visible(self, curr_song_time:float) -> None:
        latest_visible_time = curr_song_time + self.visible_note_window
        while self.map_state.upcoming and self.map_state.upcoming[0].start_time < latest_visible_time:
            new_note = self.map_state.upcoming.popleft()
            self.visible_notes.append(new_note)

    def _remove_hit_notes(self) -> list[ManiaObject]:
        to_judge: list[ManiaObject] = []
        for column, note in enumerate(self.tappable_notes):
            if note is None:
                continue
            if note.is_slider:
                if note.hit_time is not None and note.release_time is not None:
                    to_judge.append(note)
                    self.tappable_notes[column] = None
                    self.visible_notes.remove(note)
            elif note.hit_time is not None:
                to_judge.append(note)
                self.tappable_notes[column] = None
                self.visible_notes.remove(note)
        return to_judge


        

