from collections import deque

from gameplay.models import ManiaMapState, ManiaObject


def _parse_sections(content: str) -> dict[str, list[str]]:
    """Split .osu file content into named sections.

    Lines between section headers (e.g. ``[Difficulty]``) are grouped under
    that section name. Blank lines and ``//`` comments are skipped.

    Args:
        content: Full text of an .osu beatmap file.

    Returns:
        Mapping of section name to the non-empty lines belonging to it. Non empty lines returned as list of strings.
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)

    return sections


def _parse_key_values(lines: list[str]) -> dict[str, str]:
    """Parse ``key: value`` lines from a beatmap section.

    Args:
        lines: Lines from a section such as ``[Difficulty]``.

    Returns:
        Mapping of key to value, with surrounding whitespace stripped.
    """
    values: dict[str, str] = {}
    for line in lines:
        key, _, value = line.partition(":")
        if key:
            values[key.strip()] = value.strip()
    return values


def load_map(map_path: str) -> ManiaMapState:
    """Load a mania beatmap from an .osu file.

    Reads ``CircleSize`` and ``OverallDifficulty`` from ``[Difficulty]``, then
    parses ``[HitObjects]`` into ``ManiaObject`` instances. Hold notes are
    detected with ``type_flags & 128``; tap notes use ``end_time=start_time``.
    Args:
        map_path: Path to the .osu beatmap file.

    Returns:
        Map state with ``num_keys``, ``od``, and a sorted ``upcoming`` list.

    Raises:
        ValueError: If required difficulty fields are missing or invalid.
    """
    with open(map_path, "r", encoding="utf-8") as file:
        content = file.read()

    sections = _parse_sections(content)
    difficulty = _parse_key_values(sections.get("Difficulty", []))

    try:
        num_keys = int(float(difficulty["CircleSize"]))
        od = int(float(difficulty["OverallDifficulty"]))
    except KeyError as exc:
        raise ValueError(f"Missing field in {map_path}: {exc.args[0]}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid difficulty in {map_path}") from exc

    upcoming: list[ManiaObject] = []
    for line in sections.get("HitObjects", []):
        parts = line.split(",")
        if len(parts) < 4:
            continue

        x = int(parts[0])
        start_time = int(parts[2])
        slider_flag = int(parts[3])
        extra = parts[5] if len(parts) > 5 else ""
        column = int(x * num_keys / 512)

        start_time = float(start_time)
        end_time = start_time
        if slider_flag & 128:  # Mask to extract slider flag
            end_time = float(int(extra.split(":")[0]))

        upcoming.append(
            ManiaObject(
                start_time=start_time,
                column=column,
                end_time=end_time,
            )
        )

    upcoming.sort(key=lambda obj: (obj.start_time))

    return ManiaMapState(od=od, num_keys=num_keys, upcoming=deque(upcoming))

if __name__ == "__main__":
    map_path = "gameplay/xi - FREEDOM DiVE (razlteh) [4K Normal].txt"
    map_state = load_map(map_path)
    print(map_state)