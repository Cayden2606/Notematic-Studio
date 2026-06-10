"""Convert a MIDI file into a JSON array of Minecraft note-block GROUPS.

Minecraft runs at 20 game ticks/second (1 tick = 0.05 s). A redstone tick
= 2 game ticks = 0.1 s. Repeaters can only delay in whole redstone ticks,
so onsets are quantized to the 0.1 s redstone grid and the delay between
groups is always a whole number.

Notes that land on the same tick are collected into one GROUP (a chord).
A group with a single note is just a group of one. Output is a list of
groups sorted by time:
  {
    "group_index": 0,
    "redstoneTickDelay": 0,      # whole redstone ticks since previous group
    "startTick": 0,              # absolute game tick from song start
    "chords": [
      {
        "block": "minecraft:dirt",   # block placed under the note block
        "pitch": "A#",               # pitch name (note value % 12)
        "note": 16,                  # note value 0..24 (0 for percussion)
        "instrument": "harp",
        "trackName": "Piano"
      },
      ...
    ]
  }

Usage:
  python midi_to_json.py input.mid [-o output.json] [--tpr N]

  python midi_to_json.py song.mid --round-half-up
  python midi_to_json.py song.mid --no-round-half-up
"""

import argparse
import json
import math
import sys

import mido

from noteblock_data import (
    INSTRUMENTS,
    PITCH_NAMES,
    PERCUSSION,
    gm_program_to_instrument,
    gm_drum_to_instrument,
)

GAME_TICK_SECONDS = 0.05      # 20 TPS
REDSTONE_TICK_SECONDS = 0.1   # 1 redstone tick = 2 game ticks

# After octave_fit() shifts out-of-range notes into the playable range, two
# originally-distinct notes can collapse onto the SAME instrument+pitch within
# the same tick (e.g. C2 and C5 both fold to C3). Stacking duplicate note
# blocks on one tick is redundant — they produce one indistinguishable sound.
# When True, such duplicates are removed from each chord. Set to False to keep
# every note exactly as written (no dedup).
DEDUP_CHORD_NOTES = True


def round_half(value, half_up=True):
    """Round to nearest integer, with .5 ties going up or down explicitly."""
    lower = math.floor(value)
    fraction = value - lower
    if fraction > 0.5:
        return lower + 1
    if fraction < 0.5:
        return lower
    return lower + 1 if half_up else lower


def build_tempo_map(mid):
    """Return a sorted list of (abs_tick, tempo_us_per_beat) tempo changes.

    Tempo events can live on any track; gather them all against absolute
    ticks so we can convert any track's tick position to seconds.
    """
    changes = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "set_tempo":
                changes.append((abs_tick, msg.tempo))
    changes.sort(key=lambda c: c[0])
    if not changes or changes[0][0] != 0:
        # Default 120 BPM (500000 us/beat) until the first explicit tempo.
        changes.insert(0, (0, 500000))
    return changes


def tick_to_seconds(abs_tick, tempo_map, ticks_per_beat):
    """Convert an absolute MIDI tick to seconds, honoring tempo changes."""
    seconds = 0.0
    prev_tick = 0
    tempo = tempo_map[0][1]
    for change_tick, change_tempo in tempo_map:
        if change_tick >= abs_tick:
            break
        seconds += mido.tick2second(change_tick - prev_tick, ticks_per_beat, tempo)
        prev_tick = change_tick
        tempo = change_tempo
    seconds += mido.tick2second(abs_tick - prev_tick, ticks_per_beat, tempo)
    return seconds


def octave_fit(midi_note, low, high):
    """Shift midi_note by whole octaves until it lands in [low, high].

    Returns (fitted_note, out_of_range) where out_of_range is True if the
    note could not be fit even after octave shifting (then it is clamped).
    """
    n = midi_note
    while n < low:
        n += 12
    while n > high:
        n -= 12
    if n < low or n > high:
        # Span < one octave is impossible here (range is always 24), but
        # guard anyway by clamping to the nearest valid note value.
        return max(low, min(high, n)), True
    return n, False


def convert(path, tpr=1, round_half_up=True, disable_octave_limit=False, disable_ticking_limit=False):
    """Parse a MIDI file and return (groups, summary).

    Onsets are quantized to the redstone-tick grid (every 2 game ticks) so
    that the per-group redstoneTickDelay is always a whole number. `tpr`
    further coarsens the grid: tpr=1 -> 2 game ticks (1 redstone tick),
    tpr=2 -> 4 game ticks (2 redstone ticks), etc. When a value lands exactly
    on .5, `round_half_up=True` rounds upward and `False` rounds downward.
    """
    mid = mido.MidiFile(path)
    tempo_map = build_tempo_map(mid)
    tpb = mid.ticks_per_beat

    # Quantum in game ticks: if ticking limit is disabled, we quantize to 1 game tick (50ms).
    if disable_ticking_limit:
        quantum = 1
    else:
        quantum = 2 * max(1, tpr)

    notes = []  # flat list of (game_tick, note_dict)
    out_of_range = 0
    instruments_used = set()

    for track_index, track in enumerate(mid.tracks):
        abs_tick = 0
        track_name = ""
        # program per channel; default 0 (piano).
        program = {ch: 0 for ch in range(16)}

        for msg in track:
            abs_tick += msg.time
            if msg.type == "track_name":
                track_name = msg.name
            elif msg.type == "program_change":
                program[msg.channel] = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                seconds = tick_to_seconds(abs_tick, tempo_map, tpb)
                game_tick = round_half(seconds / GAME_TICK_SECONDS, half_up=round_half_up)
                # Snap to the redstone grid (whole redstone ticks between groups).
                game_tick = round_half(game_tick / quantum, half_up=round_half_up) * quantum

                if msg.channel == 9:
                    instrument = gm_drum_to_instrument(msg.note)
                else:
                    instrument = gm_program_to_instrument(program[msg.channel], msg.channel)

                info = INSTRUMENTS[instrument]
                if instrument in PERCUSSION:
                    note_value = 0
                    pitch = PITCH_NAMES[0]
                else:
                    if disable_octave_limit:
                        note_value = msg.note - info["low_midi"]
                        pitch = PITCH_NAMES[note_value % 12]
                    else:
                        fitted, oor = octave_fit(msg.note, info["low_midi"], info["high_midi"])
                        if oor:
                            out_of_range += 1
                        note_value = fitted - info["low_midi"]
                        pitch = PITCH_NAMES[note_value % 12]

                instruments_used.add(instrument)
                notes.append((game_tick, {
                    "block": info["block"],
                    "pitch": pitch,
                    "note": note_value,
                    "instrument": instrument,
                    "trackName": track_name,
                }))

    # Group notes that share the same start tick into chords.
    by_tick = {}
    for game_tick, note in notes:
        by_tick.setdefault(game_tick, []).append(note)

    # Drop redundant duplicates left over after octave_fit() folded notes into
    # range: within one tick, two notes with the same instrument AND pitch play
    # an identical sound, so the extra note block adds nothing. Disable by
    # setting DEDUP_CHORD_NOTES = False above to keep every note as written.
    if DEDUP_CHORD_NOTES:
        deduped_notes = 0
        for tick, chord in by_tick.items():
            seen = set()
            unique = []
            for note in chord:
                key = (note["instrument"], note["note"])
                if key in seen:
                    deduped_notes += 1
                    continue
                seen.add(key)
                unique.append(note)
            by_tick[tick] = unique
    else:
        deduped_notes = 0

    groups = []
    prev_tick = 0
    for group_index, tick in enumerate(sorted(by_tick)):
        gap_game_ticks = tick - prev_tick
        # If ticking limit is disabled, redstoneTickDelay can be fractional (e.g. gap_game_ticks/2)
        delay = gap_game_ticks / 2
        if delay.is_integer():
            delay = int(delay)
        groups.append({
            "group_index": group_index,
            "redstoneTickDelay": delay,
            "startTick": tick,
            "chords": by_tick[tick],
        })
        prev_tick = tick

    last_tick = groups[-1]["startTick"] if groups else 0
    summary = {
        "notes": len(notes),
        "groups": len(groups),
        "tracks": len(mid.tracks),
        "instruments_used": sorted(instruments_used),
        "out_of_range": out_of_range,
        "deduped_notes": deduped_notes,
        "length_ticks": last_tick,
        "length_seconds": round(last_tick * GAME_TICK_SECONDS, 2),
    }
    return groups, summary


def _self_test():
    """Sanity checks for octave_fit, pitch math, and tie rounding."""
    # F#1 (30) into harp range (54..78) -> shifts up two octaves to F#3 (54).
    fitted, oor = octave_fit(30, 54, 78)
    assert fitted == 54 and not oor, (fitted, oor)
    # F#7 (102) into harp range -> shifts down to F#5 (78).
    fitted, oor = octave_fit(102, 54, 78)
    assert fitted == 78 and not oor, (fitted, oor)
    # A4 (69) is in harp range already.
    fitted, oor = octave_fit(69, 54, 78)
    assert fitted == 69 and not oor, (fitted, oor)
    assert PITCH_NAMES[(69 - 54) % 12] == "A", PITCH_NAMES[(69 - 54) % 12]
    assert round_half(1.5, half_up=True) == 2
    assert round_half(2.5, half_up=True) == 3
    assert round_half(1.5, half_up=False) == 1
    assert round_half(2.5, half_up=False) == 2
    print("self-test OK")


def main():
    ap = argparse.ArgumentParser(description="MIDI -> Minecraft note-block JSON")
    ap.add_argument("input", nargs="?", help="input .mid file")
    ap.add_argument("-o", "--output", help="output .json file (default: <input>.json)")
    ap.add_argument("--tpr", type=int, default=1,
                    help="quantize onsets to this many game ticks (1=50ms grid, 2=redstone grid)")
    ap.add_argument(
        "--round-half-up",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="if true, x.5 rounds up; if false, x.5 rounds down",
    )
    ap.add_argument("--disable-octave-limit", action="store_true", help="disable the minecraft 2-octave limit")
    ap.add_argument("--disable-ticking-limit", action="store_true", help="disable redstone 0.1s quantization limit")
    ap.add_argument("--self-test", action="store_true", help="run internal sanity checks and exit")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        return
    if not args.input:
        ap.error("input .mid file required")

    groups, summary = convert(
        args.input,
        tpr=args.tpr,
        round_half_up=args.round_half_up,
        disable_octave_limit=args.disable_octave_limit,
        disable_ticking_limit=args.disable_ticking_limit,
    )
    out_path = args.output or (args.input.rsplit(".", 1)[0] + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(groups, f, indent=2)

    print(f"Wrote {summary['groups']} groups ({summary['notes']} notes) -> {out_path}")
    print(f"  tracks: {summary['tracks']}  length: {summary['length_ticks']} ticks "
          f"({summary['length_seconds']}s)")
    print(f"  instruments: {', '.join(summary['instruments_used'])}")
    if summary["out_of_range"]:
        print(f"  WARNING: {summary['out_of_range']} notes clamped (out of 6-octave range)",
              file=sys.stderr)


if __name__ == "__main__":
    main()
