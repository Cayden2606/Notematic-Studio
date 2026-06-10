"""Reference tables for Minecraft note blocks.

Facts (Minecraft Wiki, https://minecraft.wiki/w/Note_Block):
  - Each instrument plays 25 pitches: note value 0..24.
  - Note value 0 is always an F#; value 12 is the instrument's "natural"
    pitch (playback multiplier 1.0); value 24 is two octaves above value 0.
  - The block placed UNDERNEATH the note block selects the instrument.
  - Combined range across instruments is MIDI 30 (F#1) .. 102 (F#7).

MIDI numbering convention used here: middle C = C4 = 60, A4 = 69,
so F#3 = 54, F#1 = 30, F#5 = 78, F#7 = 102.
"""

# note value 0 == F#. Index a pitch name by (note_value % 12).
PITCH_NAMES = ["F#", "G", "G#", "A", "A#", "B",
               "C", "C#", "D", "D#", "E", "F"]

# Each instrument: the block placed underneath, and low_midi = the MIDI
# number of note value 0 (always an F#). high_midi = low_midi + 24.
#
# Pitched instruments share the same 25 steps, shifted by octaves:
#   bass / didgeridoo : F#1 (30) .. F#3 (54)
#   guitar            : F#2 (42) .. F#4 (66)
#   harp & friends    : F#3 (54) .. F#5 (78)
#   flute / cow_bell  : F#4 (66) .. F#6 (90)
#   bell/chime/xylo   : F#5 (78) .. F#7 (102)
INSTRUMENTS = {
    # ---- pitched ----
    "bass":          {"block": "minecraft:oak_planks",   "low_midi": 30},
    "didgeridoo":    {"block": "minecraft:pumpkin",      "low_midi": 30},
    "guitar":        {"block": "minecraft:white_wool",   "low_midi": 42},
    "harp":          {"block": "minecraft:dirt",         "low_midi": 54},
    "iron_xylophone":{"block": "minecraft:iron_block",   "low_midi": 54},
    "bit":           {"block": "minecraft:emerald_block","low_midi": 54},
    "banjo":         {"block": "minecraft:hay_block",    "low_midi": 54},
    "pling":         {"block": "minecraft:glowstone",    "low_midi": 54},
    "trumpet":       {"block": "minecraft:copper_block", "low_midi": 54},
    "flute":         {"block": "minecraft:clay",         "low_midi": 66},
    "cow_bell":      {"block": "minecraft:soul_sand",    "low_midi": 66},
    "bell":          {"block": "minecraft:gold_block",   "low_midi": 78},
    "chime":         {"block": "minecraft:packed_ice",   "low_midi": 78},
    "xylophone":     {"block": "minecraft:bone_block",   "low_midi": 78},
    # ---- percussion (pitch ignored; note value left at 0) ----
    "snare":         {"block": "minecraft:sand",         "low_midi": None},
    "hat":           {"block": "minecraft:glass",        "low_midi": None},
    "basedrum":      {"block": "minecraft:stone",        "low_midi": None},
}

# Add high_midi for every pitched instrument.
for _name, _info in INSTRUMENTS.items():
    _info["high_midi"] = None if _info["low_midi"] is None else _info["low_midi"] + 24

PERCUSSION = {"snare", "hat", "basedrum"}


def gm_program_to_instrument(program, channel):
    """Map a General MIDI program (0..127) + channel (0-indexed) to a note
    block instrument name.

    Channel 9 (the GM percussion channel, "channel 10" when 1-indexed) is
    handled per-note by gm_drum_to_instrument, so callers should check that
    first. This function returns a default percussion of 'basedrum' for
    channel 9 only as a fallback.
    """
    if channel == 9:
        return "basedrum"  # fallback; real drum mapping is per-note

    # GM families (program ranges). Picked to use distinct note-block timbres.
    if   0  <= program <= 7:   return "harp"        # Piano
    elif 8  <= program <= 15:  return "bit"         # Chromatic percussion
    elif 16 <= program <= 23:  return "pling"       # Organ
    elif 24 <= program <= 31:  return "guitar"      # Guitar
    elif 32 <= program <= 39:  return "bass"        # Bass
    elif 40 <= program <= 47:  return "harp"        # Strings
    elif 48 <= program <= 55:  return "harp"        # Ensemble
    elif 56 <= program <= 63:  return "trumpet"     # Brass
    elif 64 <= program <= 71:  return "flute"       # Reed
    elif 72 <= program <= 79:  return "flute"       # Pipe
    elif 80 <= program <= 87:  return "bit"         # Synth lead
    elif 88 <= program <= 95:  return "harp"        # Synth pad
    elif 96 <= program <= 103: return "bit"         # Synth effects
    elif 104 <= program <= 111:return "banjo"       # Ethnic
    elif 112 <= program <= 119:return "iron_xylophone"  # Percussive
    else:                      return "harp"        # Sound effects (120-127)


def gm_drum_to_instrument(midi_note):
    """Map a General MIDI percussion key (channel 10) to one of the three
    note-block drum sounds: snare / hat / basedrum.

    GM drum map key numbers: https://en.wikipedia.org/wiki/General_MIDI#Percussion
    """
    # Kick / low toms / low percussion -> bass drum
    if midi_note in (35, 36, 41, 43, 45, 47, 64):
        return "basedrum"
    # Snares, claps, rimshot, mid/high toms -> snare
    if midi_note in (37, 38, 39, 40, 48, 50, 60, 61, 62, 63, 65, 66):
        return "snare"
    # Hi-hats, cymbals, shakers, triangles, high percussion -> hat
    return "hat"
