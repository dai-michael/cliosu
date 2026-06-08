import curses

from gameplay.models import GameStats, RenderM

CellState = tuple[bool, bool, int]


class GameRenderer:
    """Renders osu!mania-style gameplay in the terminal using curses."""

    LANE_WIDTH = 6
    KEY_LABELS = ("D", "F", "J", "K")
    BLOCK_TOP = "▀"
    BLOCK_BOTTOM = "▄"
    BLOCK_FULL = "█"

    COLOR_PURPLE = 1
    COLOR_CYAN = 2
    COLOR_JUDGMENT = 3
    COLOR_STATS = 4
    COLOR_DIM = 5
    COLOR_PRESSED = 6

    def __init__(self, stdscr: curses.window, num_columns: int = 4, height: int = 40, width:int = 100) -> None:
        """Bind the curses window and compute initial layout."""
        self.stdscr = stdscr
        self.num_columns = num_columns
        self.height = height
        self.width = width
        self._setup_curses()
        self._layout()

    @property
    def judgment_half_y(self) -> int:
        """Bottom half-row index aligned with the judgment line."""
        return self.judgment_y * 2 + 1

    def _setup_curses(self) -> None:
        """Configure non-blocking input, hide cursor, and init color pairs."""
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(0)
        self.stdscr.keypad(True)

        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(self.COLOR_PURPLE, curses.COLOR_MAGENTA, -1)
            curses.init_pair(self.COLOR_CYAN, curses.COLOR_CYAN, -1)
            curses.init_pair(self.COLOR_JUDGMENT, curses.COLOR_WHITE, -1)
            curses.init_pair(self.COLOR_STATS, curses.COLOR_YELLOW, -1)
            curses.init_pair(self.COLOR_DIM, curses.COLOR_WHITE, -1)
            curses.init_pair(self.COLOR_PRESSED, curses.COLOR_RED, -1)

    def _layout(self) -> None:
        """Recompute playfield, stats panel, and judgment line positions."""
        #height, width = self.stdscr.getmaxyx()

        playfield_inner = self.num_columns * self.LANE_WIDTH + (self.num_columns - 1)
        stats_width = 16 
        total_width = playfield_inner + 2 + stats_width
        self.playfield_left = max(0, (self.width - total_width) // 2)
        self.stats_left = min(self.width - stats_width, self.playfield_left + playfield_inner + 2)
        self.judgment_y = max(4, self.height - 4)
        self.receptor_y = min(self.height - 2, self.judgment_y + 2)

    def render(
        self,
        hitobjects: list[RenderM],
        stats: GameStats,
        pressed_columns: list[int],
    ) -> None:
        """Clear the screen and draw one full gameplay frame."""
        #height, width = self.stdscr.getmaxyx()
        height,width=self.height,self.width
        if (height, width) != (self.height, self.width):
            self._layout()

        self.stdscr.erase()
        self._draw_playfield()

        note_buffer: dict[tuple[int, int], CellState] = {}
        for hitobject in hitobjects:
            self._accumulate_hitobject(note_buffer, hitobject) # Add hitobjects to draw buffer
        self._flush_note_buffer(note_buffer) # Write buffered note cells to the screen as block characters.

        self._draw_judgment_line(pressed_columns)
        self._draw_receptors()
        self._draw_stats(stats)
        self._draw_combo(stats)
        self.stdscr.refresh()

    def _lane_x(self, column: int) -> int:
        """Return the left x coordinate for a lane column."""
        return self.playfield_left + column * (self.LANE_WIDTH + 1)

    def _column_attr(self, column: int) -> int:
        """Return bold curses attributes for notes in the given column."""
        color = self.COLOR_PURPLE if column in (0, self.num_columns - 1) else self.COLOR_CYAN
        attr = curses.color_pair(color) if curses.has_colors() else curses.A_NORMAL
        return attr | curses.A_BOLD

    def _draw_playfield(self) -> None:
        """Draw dim lane backgrounds and vertical dividers."""
        dim = curses.color_pair(self.COLOR_DIM) if curses.has_colors() else curses.A_DIM
        top = 1
        bottom = min(self.judgment_y, self.height - 1)

        for row in range(top, bottom):
            for column in range(self.num_columns):
                x = self._lane_x(column)
                self._safe_hline(row, x, self.LANE_WIDTH, " ", dim)
                if column < self.num_columns - 1:
                    self._safe_addch(row, x + self.LANE_WIDTH, ord("|"), dim)

    def _accumulate_hitobject(
        self,
        buffer: dict[tuple[int, int], CellState],
        hitobject: RenderM,
    ) -> None:
        """Add a note or slider's occupied cells into the draw buffer."""
        if hitobject.column < 0 or hitobject.column >= self.num_columns:
            return

        x = self._lane_x(hitobject.column)
        attr = self._column_attr(hitobject.column)

        if hitobject.is_slider:
            end_y = hitobject.end_y
            top = min(hitobject.start_y, end_y)
            bottom = max(hitobject.start_y, end_y)
            for half_y in range(top, bottom + 1): 
                row = half_y // 2
                half = half_y % 2
                if half_y == hitobject.start_y: 
                    self._buffer_fill_lane(buffer, row, x, half, attr)
                else: # Draw slider body
                    center_x = x + self.LANE_WIDTH // 2
                    self._buffer_fill_half(buffer, row, center_x, half, attr)
                    self._buffer_fill_half(buffer, row, center_x - 1, half, attr)
        else:
            row = hitobject.start_y // 2
            half = hitobject.start_y % 2
            self._buffer_fill_lane(buffer, row, x, half, attr)

    def _buffer_fill_lane(
        self,
        buffer: dict[tuple[int, int], CellState],
        row: int,
        x: int,
        half: int,
        attr: int,
    ) -> None:
        """ Draws the hitobject - currently hardcoded for lanes
        Mark every cell in a lane row for the given half-row."""
        for dx in range(self.LANE_WIDTH):
            self._buffer_fill_half(buffer, row, x + dx, half, attr)

    def _buffer_fill_half(
        self,
        buffer: dict[tuple[int, int], CellState],
        row: int,
        x: int,
        half: int,
        attr: int,
    ) -> None:
        """Mark one cell's top or bottom half in the draw buffer."""
        key = (row, x)
        top, bottom, _ = buffer.get(key, (False, False, attr))
        if half == 0:
            buffer[key] = (True, bottom, attr)
        else:
            buffer[key] = (top, True, attr)

    def _flush_note_buffer(self, buffer: dict[tuple[int, int], CellState]) -> None:
        """Write buffered note cells to the screen as block characters."""
        for (row, x), (top, bottom, attr) in buffer.items():
            if top and bottom:
                ch = self.BLOCK_FULL
            elif top:
                ch = self.BLOCK_TOP
            elif bottom:
                ch = self.BLOCK_BOTTOM
            else:
                continue
            self._safe_addstr(row, x, ch, attr)

    def _draw_judgment_line(self, pressed_columns: list[int]) -> None:
        """Draw the horizontal line where notes are judged."""
        default_attr = (
            curses.color_pair(self.COLOR_JUDGMENT) if curses.has_colors() else curses.A_BOLD
        )
        pressed_attr = (
            curses.color_pair(self.COLOR_PRESSED) if curses.has_colors() else curses.A_BOLD
        )
        pressed = set(pressed_columns)

        for column in range(self.num_columns):
            x = self._lane_x(column)
            attr = pressed_attr if column in pressed else default_attr
            self._safe_hline(self.judgment_y, x, self.LANE_WIDTH, "─", attr)
            if column < self.num_columns - 1:
                self._safe_addch(
                    self.judgment_y,
                    x + self.LANE_WIDTH,
                    ord("|"),
                    default_attr,
                )

    def _draw_receptors(self) -> None:
        """Draw key labels centered under each lane."""
        dim = curses.color_pair(self.COLOR_DIM) if curses.has_colors() else curses.A_DIM
        for column in range(min(self.num_columns, len(self.KEY_LABELS))):
            x = self._lane_x(column)
            label = self.KEY_LABELS[column]
            label_x = x + (self.LANE_WIDTH - len(label)) // 2
            self._safe_addstr(self.receptor_y, label_x, label, dim)

    def _draw_stats(self, stats: GameStats) -> None:
        """Draw accuracy and combo in the side stats panel."""
        attr = curses.color_pair(self.COLOR_STATS) if curses.has_colors() else curses.A_BOLD
        lines = [
            "Accuracy",
            f"{stats.accuracy:6.2f}%",
            "",
            "Combo",
            f"{stats.combo:,}",
        ]
        for index, line in enumerate(lines):
            self._safe_addstr(1 + index, self.stats_left, line, attr if index in (0, 3) else curses.A_NORMAL)

    def _draw_combo(self, stats: GameStats) -> None:
        """Draw a large combo counter above the judgment line."""
        if stats.combo <= 0:
            return

        combo_text = f"{stats.combo:,}"
        playfield_width = self.num_columns * self.LANE_WIDTH + (self.num_columns - 1)
        x = self.playfield_left + max(0, (playfield_width - len(combo_text)) // 2)
        y = max(2, self.judgment_y - 3)
        attr = curses.color_pair(self.COLOR_STATS) if curses.has_colors() else curses.A_BOLD
        self._safe_addstr(y, x, combo_text, attr | curses.A_BOLD)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        """Write a string, clipping at screen edges and ignoring curses errors."""
        if y < 0 or y >= self.height or x >= self.width:
            return
        max_len = self.width - x - 1
        if max_len <= 0:
            return
        try:
            self.stdscr.addstr(y, x, text[:max_len], attr)
        except curses.error:
            pass

    def _safe_addch(self, y: int, x: int, ch: int, attr: int = 0) -> None:
        """Write a single character, ignoring out-of-bounds and curses errors."""
        if y < 0 or y >= self.height or x < 0 or x >= self.width:
            return
        try:
            self.stdscr.addch(y, x, ch, attr)
        except curses.error:
            pass

    def _safe_hline(self, y: int, x: int, length: int, ch: str, attr: int = 0) -> None:
        """Draw a horizontal line of repeated characters via _safe_addstr."""
        if length <= 0:
            return
        self._safe_addstr(y, x, ch * length, attr)
