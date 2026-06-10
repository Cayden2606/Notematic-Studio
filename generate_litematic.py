"""Generate a simple Litematica schematic from note-block JSON groups.

This is a first-pass builder focused on producing a valid `.litematic` file
from `output.json`. The layout follows a simple note-block bus:

- A main repeater backbone runs along +Z.
- Each group's `redstoneTickDelay` is encoded as a chain of directional
  repeaters.
- Every group ends on a repeater that points into the chord.
- Groups with 1..3 notes are placed directly in front of that repeater.
- Groups with 4+ notes use trigger repeater -> dust row -> 1-tick repeater row
  -> note row.

The resulting schematic is timing-aware and easy to inspect, but it is still a
minimal starter layout rather than a polished compact song machine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from litemapy import BlockState, Region, Schematic


STONE = BlockState("minecraft:stone")
REDSTONE_DUST = BlockState("minecraft:redstone_wire")
START_NOTE_SUPPORT = BlockState("minecraft:dirt")


def load_groups(path: Path) -> list[dict]:
    """Load group data from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "groups" in data and isinstance(data["groups"], list):
            data = data["groups"]
        else:
            raise ValueError("JSON object must contain a top-level 'groups' list")
    if not isinstance(data, list):
        raise ValueError("Expected a JSON list of groups")
    return data


def split_delay(delay: int) -> list[int]:
    """Split a redstone-tick delay into repeater delays of 1..4."""
    if delay < 0:
        raise ValueError(f"Delay cannot be negative: {delay}")
    parts: list[int] = []
    remaining = delay
    while remaining > 0:
        part = min(4, remaining)
        parts.append(part)
        remaining -= part
    return parts


def group_pattern_depth(group: dict) -> int:
    """Return how many rows a group's local pattern uses after its delay chain."""
    return 3 if len(group.get("chords", [])) >= 4 else 1


def group_delay_chain(group: dict) -> list[int]:
    """Return the repeater chain delays before a group's local pattern."""
    delay = int(float(group["redstoneTickDelay"]))
    if len(group.get("chords", [])) >= 4:
        delay = max(0, delay - 1)
    return split_delay(delay)


def plan_layout(groups: list[dict]) -> tuple[list[int], int]:
    """Return chain-end Z positions for groups and the max used Z coordinate."""
    chain_ends: list[int] = []
    current_end_z = 2
    chain_ends.append(current_end_z)

    for previous_group, group in zip(groups, groups[1:]):
        current_end_z += group_pattern_depth(previous_group)
        current_end_z += len(group_delay_chain(group))
        chain_ends.append(current_end_z)

    max_used_z = max(
        chain_end + group_pattern_depth(group)
        for chain_end, group in zip(chain_ends, groups)
    )
    return chain_ends, max_used_z


def set_block(region: Region, x: int, y: int, z: int, block: BlockState) -> None:
    """Compatibility wrapper for block placement."""
    region[x, y, z] = block


def centered_x_positions(count: int, center_x: int) -> list[int]:
    """Return centered X positions for a note row."""
    start_x = center_x - ((count - 1) // 2)
    return [start_x + index for index in range(count)]


def place_note(region: Region, x: int, y: int, z: int, chord: dict) -> None:
    """Place one note block with the correct support block beneath it."""
    block_id = chord["block"]
    if "copper" in block_id and "waxed" not in block_id:
        if block_id.startswith("minecraft:"):
            block_id = block_id.replace("minecraft:", "minecraft:waxed_")
        else:
            block_id = f"waxed_{block_id}"

    set_block(region, x, y - 1, z, BlockState(block_id))
    
    # Clamp note blocks to standard Minecraft 0..24 range for Litematica compliance.
    note_val = max(0, min(24, int(chord["note"])))
    
    set_block(
        region,
        x,
        y,
        z,
        BlockState(
            "minecraft:note_block",
            instrument=chord["instrument"],
            note=str(note_val),
            powered="false",
        ),
    )


def place_small_group(region: Region, center_x: int, chain_end_z: int, chords: list[dict]) -> None:
    """Place a 1..3 note chord directly after its repeater chain."""
    note_z = chain_end_z + 1
    for x, chord in zip(centered_x_positions(len(chords), center_x), chords):
        place_note(region, x, 1, note_z, chord)


def place_large_group(region: Region, center_x: int, chain_end_z: int, chords: list[dict]) -> None:
    """Place a 4+ note chord using dust into a 1-tick repeater row."""
    dust_z = chain_end_z + 1
    repeater_z = chain_end_z + 2
    note_z = chain_end_z + 3
    x_positions = centered_x_positions(len(chords), center_x)

    for x in x_positions:
        set_block(region, x, 0, dust_z, STONE)
        set_block(region, x, 1, dust_z, REDSTONE_DUST)
        set_block(region, x, 0, repeater_z, STONE)
        set_block(
            region,
            x,
            1,
            repeater_z,
            BlockState("minecraft:repeater", facing="north", delay="1", locked="false", powered="false"),
        )

    for x, chord in zip(x_positions, chords):
        place_note(region, x, 1, note_z, chord)


def build_region(groups: list[dict]) -> Region:
    """Build a simple region containing the repeater spine and note blocks."""
    if not groups:
        raise ValueError("No groups found in JSON")

    chain_end_positions, max_used_z = plan_layout(groups)
    max_chord = max(len(group.get("chords", [])) for group in groups)
    max_chord = max(1, max_chord)
    center_x = max_chord + 1

    width = (2 * max_chord) + 3
    height = 4
    length = max_used_z + 2

    region = Region(0, 0, 0, width, height, length)

    # Starter input:
    # repeater, then observer behind it, then note block with a chain on top.
    set_block(region, center_x, 0, 0, START_NOTE_SUPPORT)
    set_block(
        region,
        center_x,
        1,
        0,
        BlockState("minecraft:note_block", instrument="harp", note="0", powered="false"),
    )
    set_block(region, center_x, 2, 0, BlockState("minecraft:chain", axis="y"))
    set_block(region, center_x, 0, 1, STONE)
    set_block(region, center_x, 1, 1, BlockState("minecraft:observer", facing="north", powered="false"))

    # Starter repeater chain end for the first group.
    set_block(region, center_x, 0, 2, STONE)
    set_block(
        region,
        center_x,
        1,
        2,
        BlockState("minecraft:repeater", facing="north", delay="1", locked="false", powered="false"),
    )

    previous_end_z = 2
    for previous_group, group, chain_end_z in zip(groups, groups[1:], chain_end_positions[1:]):
        chain_start_z = previous_end_z + group_pattern_depth(previous_group) + 1
        delays = group_delay_chain(group)
        for offset, delay in enumerate(delays):
            z = chain_start_z + offset
            set_block(region, center_x, 0, z, STONE)
            set_block(
                region,
                center_x,
                1,
                z,
                BlockState("minecraft:repeater", facing="north", delay=str(delay), locked="false", powered="false"),
            )
        previous_end_z = chain_end_z

    for chain_end_z, group in zip(chain_end_positions, groups):
        chords = group.get("chords", [])
        if not chords:
            continue
        if len(chords) <= 3:
            place_small_group(region, center_x, chain_end_z, chords)
        else:
            place_large_group(region, center_x, chain_end_z, chords)

    return region


def build_schematic(groups: list[dict], name: str, author: str, description: str) -> Schematic:
    """Create a schematic from group data."""
    region = build_region(groups)
    return region.as_schematic(name=name, author=author, description=description)


def generate_litematic_file(
    input_path: str | Path,
    output_path: str | Path,
    name: str | None = None,
    author: str = "Codex",
) -> tuple[int, int]:
    """Load grouped JSON, write a litematic, and return (groups, notes)."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    schematic_name = name or input_path.stem
    groups = load_groups(input_path)
    description = (
        "Simple note-block layout generated from grouped JSON. "
        "Uses a north-facing repeater spine with an observer-over-note-block start input."
    )
    schematic = build_schematic(groups, schematic_name, author, description)
    schematic.save(str(output_path))
    group_count = len(groups)
    note_count = sum(len(group.get("chords", [])) for group in groups)
    return group_count, note_count


def main() -> None:
    parser = argparse.ArgumentParser(description="JSON note groups -> .litematic")
    parser.add_argument("input", nargs="?", default="output.json", help="Input JSON file")
    parser.add_argument("-o", "--output", help="Output .litematic file")
    parser.add_argument("--name", help="Schematic name")
    parser.add_argument("--author", default="Codex", help="Schematic author")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".litematic")
    group_count, note_count = generate_litematic_file(
        input_path,
        output_path,
        name=args.name,
        author=args.author,
    )
    print(f"Wrote {output_path}")
    print(f"  groups: {group_count}")
    print(f"  notes: {note_count}")


if __name__ == "__main__":
    main()
